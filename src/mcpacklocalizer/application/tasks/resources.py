"""Group recognized documents by Minecraft resource source, without rescanning files."""
from collections import Counter


def resource_type(document):
    path = document.path.replace("\\", "/").lower()
    if document.kind.startswith("patchouli-"):
        return "帕秋莉手册"
    if document.kind.startswith("ftb"):
        return "FTB Quests"
    if document.kind == "betterquesting":
        return "Better Questing"
    if path.startswith("kubejs/"):
        return {"kubejs-script": "KubeJS 脚本文本", "kubejs-asset-text": "KubeJS JSON 文本"}.get(
            document.kind, "KubeJS 语言文件")
    if document.kind == "mod-lang" or path.startswith("mod-language/"):
        return "模组语言资源"
    if path.startswith("resources/"):
        return "资源包语言文件"
    return "其它语言资源"


def resource_groups(scan):
    counts = Counter(entry.document for entry in scan.entries)
    groups = {}
    for document in scan.documents:
        groups.setdefault(resource_type(document), []).append((document.path, counts[document.path]))
    return {key: sorted(value) for key, value in groups.items()}
