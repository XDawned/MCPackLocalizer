# [Module: tasks.polishing] [Status: 已完成] [Brief: 有界并发修润候选、失败内容保留与人工校验接受]
from __future__ import annotations

import json
import sys
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict

from ...core.mods.combined import mod_scan
from ...core.mods.tasks import validate_mod_translation
from ...core.pack.extraction import resource_exclusions
from ...core.pack.patch import validate_sources
from ...core.translation.local import quality_warnings, validate_entry, validate_manual_entry
from ...core.translation.polishing import PolishApiClient
from ...core.translation.rules import NoTranslate


def polish_results(client, entries, args, concurrency):
    def revise(entry):
        try:
            return client.propose(entry.source, entry.translation, entry.context, args.polish_prompt,
                                  args.polish_mode, script=bool(entry.script))
        except (ValueError, RuntimeError, OSError) as exc:
            return {"translation": None, "raw_response": "", "error": str(exc)}

    # 同时只提交并发上限数量的工作；SQLite 仍由调用线程逐条写入。
    iterator = iter(entries)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        pending = {}
        for _ in range(concurrency):
            entry = next(iterator, None)
            if entry is not None:
                pending[pool.submit(revise, entry)] = entry
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                entry = pending.pop(future)
                yield entry, future.result()
                following = next(iterator, None)
                if following is not None:
                    pending[pool.submit(revise, following)] = following


def run_polishing(store, args, config):
    scan = store.load()
    validate_sources(scan)
    config.source_locale, config.target_locale = scan.source_locale, scan.target_locale
    excluded = resource_exclusions(scan)
    by_id = {entry.id: entry for entry in scan.entries}
    if args.entry_ids is not None and set(args.entry_ids) - by_id.keys():
        raise ValueError("选中的修润条目已不存在，请重新打开任务")
    selected = [by_id[key] for key in args.entry_ids] if args.entry_ids is not None else scan.entries
    selected = [entry for entry in selected if entry.document not in excluded]
    if not selected:
        raise ValueError("没有可修润的条目")
    mods = mod_scan(scan)
    audit = {"id": args.polish_run_id, "preview_only": True, "mode": args.polish_mode,
             "prompt": args.polish_prompt, "model_config": asdict(config),
             "previous": {entry.id: {key: getattr(entry, key) for key in ("source", "context", "translation", "status", "origin", "error")}
                          for entry in selected}, "results": {}, "api_usage": {}}
    runs = scan.metadata.setdefault("polish_runs", [])
    runs.append(audit)
    # 保留最近二十批修润记录，避免多次全量操作无限增大检查点。
    del runs[:-20]
    store.metadata(scan)
    completed = failed = 0
    try:
        with PolishApiClient(config, args.credentials, config.request_timeout) as client:
            for entry, proposal in polish_results(client, selected, args, config.concurrency):
                translation, error = proposal["translation"], proposal["error"]
                try:
                    if error:
                        raise ValueError(error)
                    validate_polish_candidate(scan, entry, translation, audit, mods)
                    completed += 1
                except ValueError as exc:
                    failed += 1
                    proposal["error"] = guard_reason(entry.source, translation, str(exc))
                audit["results"][entry.id] = proposal
                audit["api_usage"] = client.usage_snapshot()
                store.metadata(scan)
                print(json.dumps({"operation": "polish", "completed": completed, "failed": failed,
                                  "remaining": len(selected) - completed - failed, "entry_id": entry.id,
                                  "error": audit["results"][entry.id]["error"], "api_usage": audit["api_usage"],
                                  "quality_warnings": quality_warnings(entry.source, translation)
                                  if translation is not None else []}, ensure_ascii=False), file=sys.stderr, flush=True)
    finally:
        store.export()
    return {"output": str(store.output), "polished_this_run": completed, "failed_this_run": failed,
            "partial": bool(failed), "api_usage": audit["api_usage"], "operation": "polish", "run_id": audit["id"]}


def guard_reason(source, translation, reason):
    from ...core.translation.local import PROTECTED

    if translation is None:
        return reason
    before, after = PROTECTED.findall(source), PROTECTED.findall(translation)
    missing, added = Counter(before) - Counter(after), Counter(after) - Counter(before)
    parts = [reason]
    if missing and "缺失保留符：" not in reason:
        parts.append("缺失保留符：" + "、".join(missing.elements()))
    if added and "新增保留符：" not in reason:
        parts.append("新增保留符：" + "、".join(added.elements()))
    if before != after and not missing and not added and "保留符顺序改变" not in reason:
        parts.append("保留符顺序改变")
    return "；".join(parts)


def validate_polish_candidate(scan, entry, translation, run, mods=None):
    if not isinstance(translation, str) or not translation.strip():
        raise ValueError("候选译文不能为空")
    try:
        validate_entry(entry, translation, False)
        task_config = scan.metadata.get("script_model_config" if entry.script else "model_config", {})
        NoTranslate(task_config.get("non_translate", "")).validate(entry.source, translation)
        NoTranslate(run.get("model_config", {}).get("non_translate", "")).validate(entry.source, translation)
        mods = mods if mods is not None else mod_scan(scan)
        if mods is not None and entry.semantic_key.startswith("mod:"):
            validate_mod_translation(mods, entry.source, translation)
    except ValueError as exc:
        raise ValueError(guard_reason(entry.source, translation, str(exc))) from None


def accept_polishing(store, args):
    scan = store.load()
    validate_sources(scan)
    run = next((run for run in scan.metadata.get("polish_runs", []) if run.get("id") == args.polish_run_id), None)
    if run is None or not run.get("preview_only"):
        raise ValueError("修润预览记录已不存在，请重新生成修润结果")
    by_id, changes = {entry.id: entry for entry in scan.entries}, []
    mods = mod_scan(scan)
    for key, translation in args.polish_updates.items():
        entry, proposal = by_id.get(key), run["results"].get(key)
        if entry is None or proposal is None or proposal.get("accepted"):
            raise ValueError("条目不存在、尚未返回或已经接受，请重新打开修润预览")
        previous = run["previous"][key]
        if any(getattr(entry, name) != value for name, value in previous.items()):
            raise ValueError("条目在生成候选结果后已被修改，请重新修润，避免覆盖新的人工编辑")
        validate_manual_entry(entry, translation)
        if mods is not None and entry.semantic_key.startswith("mod:"):
            validate_mod_translation(mods, entry.source, translation, manual=True)
        changes.append((entry, proposal, translation))
    # 先检查全部选择的回写结构，再原子提交；内容守卫由人工决定。
    for entry, proposal, translation in changes:
        entry.translation, entry.status, entry.origin, entry.error = translation, "reviewed", "manual", ""
        proposal.update(accepted=True, accepted_translation=translation,
                        edited=translation != proposal.get("translation"))
    store.update_many([entry for entry, _, _ in changes], scan)
    store.export()
    return {"operation": "polish-accept", "accepted": len(changes), "output": str(store.output)}
