"""Find text by JavaScript syntax/roles; never execute or reformat pack scripts."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from ..translation.local import validate

COLORS = {"black", "darkBlue", "darkGreen", "darkAqua", "darkRed", "darkPurple", "gold", "gray",
          "darkGray", "blue", "green", "aqua", "red", "lightPurple", "yellow", "white"}
FACTORIES = COLORS | {"of", "literal", "string"}
MESSAGES = {"tell", "setStatusMessage", "sendSystemMessage", "displayClientMessage", "sendFailure", "sendSuccess"}
SCOPES = {"program", "statement_block", "arrow_function", "function_expression", "function_declaration"}
FUNCTIONS = {"arrow_function", "function_expression", "function_declaration"}
MARKER = re.compile(r"\{\{MCPL_[a-f0-9]{12}_\d+\}\}")
EVENTS = {
    "item.tooltip": "tooltip", "client.item_tooltip": "legacy-tooltip", "jei.information": "jei-old",
    "rei.information": "rei-old", "item.registry": "registry", "block.registry": "registry",
    "ItemEvents.tooltip": "tooltip", "ItemEvents.modifyTooltips": "modify-tooltip",
    "ItemEvents.dynamicTooltips": "dynamic-tooltip", "JEIEvents.information": "jei",
    "REIEvents.information": "rei", "RecipeViewerEvents.addInformation": "viewer",
    "StartupEvents.registry": "registry",
}


def parse_script(text):
    try:
        import tree_sitter_javascript
        from tree_sitter import Language, Parser
    except ImportError:
        raise ValueError("缺少 JS 解析依赖：请安装 tree-sitter 和 tree-sitter-javascript") from None
    tree = Parser(Language(tree_sitter_javascript.language())).parse(text.encode("utf-8"))
    if tree.root_node.has_error:
        raise ValueError("JS 存在语法错误或不支持的语法；该文件不会自动回写")
    return tree


def walk(node):
    yield node
    for child in node.named_children:
        yield from walk(child)


def decode_js(raw):
    """Decode string/quasi escapes without eval; reject legacy octal escapes."""
    def escape(match):
        token = match.group(1)
        if token.startswith("u{"):
            return chr(int(token[2:-1], 16))
        if token.startswith(("u", "x")) and len(token) > 1:
            return chr(int(token[1:], 16))
        if token in {"\n", "\r", "\r\n"}:
            return ""
        if token.isdigit() and token != "0":
            raise ValueError("不自动处理 JS 旧式八进制字符串转义")
        return {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}.get(token, token)
    if re.search(r"\\0[0-9]", raw):
        raise ValueError("不自动处理 JS 旧式八进制字符串转义")
    value = re.sub(r"\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|\r\n|[\s\S])", escape, raw)
    return value.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")


def encode_js(value, quote):
    # json supplies safe control-character escaping; quote-specific escapes follow.
    body = json.dumps(value, ensure_ascii=True)[1:-1]
    if quote == "'":
        body = body.replace('\\"', '"').replace("'", "\\'")
    if quote == "`":
        return body.replace('\\"', '"').replace("`", "\\`").replace("${", "\\${")
    return quote + body + quote


def split_translation(source, translation, *, manual=False):
    if not isinstance(translation, str):
        raise ValueError("脚本译文必须是文字")  # noqa: TRY004 - rejected model output is a validation error
    if MARKER.findall(source) != MARKER.findall(translation):
        raise ValueError("脚本译文修改了表达式占位符或其顺序")
    before, after = MARKER.split(source), MARKER.split(translation)
    if len(before) != len(after):
        raise ValueError("脚本文本槽位数量发生变化")
    for original, translated in zip(before, after, strict=True):
        if not original.strip():
            if original != translated:
                raise ValueError("空白脚本槽位不能修改")
        elif not manual:
            validate(original, translated, False)
        elif not translated.strip():
            raise ValueError("脚本文字槽位不能为空")
    return after


@dataclass
class Unit:
    source: str
    script: dict
    context: str
    dependencies: set = field(default_factory=set)


class Analyzer:
    def __init__(self, text):
        self.text, self.raw = text, text.encode("utf-8")
        self.root = parse_script(text).root_node
        self.nodes = list(walk(self.root))
        self.bindings, self.roles, self.units, self.diagnostics = {}, {}, [], []
        self.allowed_refs, self.seen = set(), set()
        self.index_bindings()
        self.index_roles()

    def raw_text(self, node):
        return self.raw[node.start_byte:node.end_byte].decode("utf-8")

    def char_offset(self, offset):
        return len(self.raw[:offset].decode("utf-8"))

    def scope(self, node):
        while node is not None and node.type not in SCOPES:
            node = node.parent
        return node

    def binding(self, node):
        name, scope = self.raw_text(node), self.scope(node)
        while scope is not None:
            found = self.bindings.get((scope.id, name))
            if found:
                return found
            scope = self.scope(scope.parent)
        return None

    def bind_pattern(self, pattern, scope, value=None, const=False):
        if pattern is None:
            return
        for name in walk(pattern):
            if name.type in {"identifier", "shorthand_property_identifier_pattern"}:
                self.bindings[(scope.id, self.raw_text(name))] = {
                    "id": name.id, "value": value if pattern.type == "identifier" else None,
                    "const": const, "node": name, "mutated": False}

    def index_bindings(self):
        for node in self.nodes:
            if node.type == "variable_declarator":
                name, value = node.child_by_field_name("name"), node.child_by_field_name("value")
                self.bind_pattern(name, self.scope(node), value,
                                  bool(re.match(r"^\s*const\b", self.raw_text(node.parent))))
            elif node.type in FUNCTIONS:
                params = node.child_by_field_name("parameters") or node.child_by_field_name("parameter")
                for param in (params.named_children if params and params.type == "formal_parameters" else [params]):
                    self.bind_pattern(param, node)
            if node.type in {"function_declaration", "class_declaration"}:
                self.bind_pattern(node.child_by_field_name("name"), self.scope(node.parent))
        for node in self.nodes:
            if node.type in {"assignment_expression", "augmented_assignment_expression", "update_expression"}:
                target = node.child_by_field_name("left") or node.child_by_field_name("argument")
                if target and target.type == "identifier" and (binding := self.binding(target)):
                    binding["mutated"] = True

    def parts(self, call):
        if call.type != "call_expression":
            return None, "", []
        function = call.child_by_field_name("function")
        args = call.child_by_field_name("arguments")
        if function and function.type == "member_expression":
            values = [child for child in args.named_children if child.type != "comment"] if args else []
            return function.child_by_field_name("object"), self.raw_text(function.child_by_field_name("property")), values
        return None, self.raw_text(function) if function else "", [child for child in args.named_children
                                                                  if child.type != "comment"] if args else []

    def callback_params(self, callback):
        params = callback.child_by_field_name("parameters") or callback.child_by_field_name("parameter")
        return [child for child in params.named_children if child.type != "comment"] if params and params.type == "formal_parameters" else [params] if params else []

    def index_roles(self):
        for call in self.nodes:
            if call.type != "call_expression":
                continue
            obj, method, args = self.parts(call)
            qualified = (self.raw_text(obj) + "." if obj else "") + method
            role = EVENTS.get(qualified)
            if method == "onEvent" and not obj and args and args[0].type == "string":
                role = EVENTS.get(decode_js(self.raw_text(args[0])[1:-1]))
            if obj and obj.type == "identifier" and self.binding(obj):
                role = None  # User-defined ItemEvents/StartupEvents bindings.
            callback = next((arg for arg in args if arg.type in FUNCTIONS), None)
            if role and callback:
                for param in self.callback_params(callback)[:1]:
                    if param.type == "identifier":
                        self.roles[param.id] = role
            receiver = self.role(obj)
            if callback and receiver == "tooltip" and method in {"addAdvanced", "addAdvancedToAll"}:
                params = self.callback_params(callback)
                if len(params) >= 3:
                    self.roles[params[2].id] = "lines"
            if callback and receiver == "modify-tooltip" and method in {"modify", "modifyAll"}:
                params = self.callback_params(callback)
                if params:
                    self.roles[params[0].id] = "text-builder"

    def role(self, node, depth=0):
        if node is None or depth > 32:
            return ""
        if node.type == "identifier":
            binding = self.binding(node)
            if not binding:
                name = self.raw_text(node)
                return "text" if name in {"Text", "Component"} else "message" if name in {"player", "server"} else ""
            return self.roles.get(binding["id"], "") or (
                self.role(binding["value"], depth + 1) if binding["const"] and not binding["mutated"] else "")
        if node.type == "member_expression":
            obj, prop = node.child_by_field_name("object"), self.raw_text(node.child_by_field_name("property"))
            if prop in {"player", "server"}:
                return "message"
            if prop == "lines" and self.role(obj, depth + 1) == "dynamic-tooltip":
                return "lines"
        if node.type == "call_expression":
            obj, method, _ = self.parts(node)
            parent_role = self.role(obj, depth + 1)
            if method == "create" and parent_role == "registry":
                return "builder"
            if parent_role == "builder":
                return "builder"
            if parent_role == "text" and method in FACTORIES | {"translate", "translatable", "translateWithFallback", "translatableWithFallback"}:
                return "component"
            if parent_role == "component":
                return "component"
        return ""

    def diagnostic(self, node, reason):
        record = {"line": node.start_point.row + 1, "reason": reason, "expression": self.raw_text(node)[:300]}
        if record not in self.diagnostics:
            self.diagnostics.append(record)

    def slot(self, node, start=None, end=None, quote=None):
        raw = self.raw_text(node)
        begin, finish = node.start_byte if start is None else start, node.end_byte if end is None else end
        token = self.raw[begin:finish].decode("utf-8")
        value = decode_js(token if quote == "`" else token[1:-1])
        return {"start": self.char_offset(begin), "end": self.char_offset(finish), "raw": token,
                "value": value, "quote": quote or raw[0]}

    def emit(self, node, slots, rule, dependencies=()):
        identity = tuple((slot["start"], slot["end"]) for slot in slots)
        if not slots or identity in self.seen:
            return
        self.seen.add(identity)
        shape = self.raw_text(node)
        prefix = hashlib.sha256((rule + shape).encode()).hexdigest()[:12]
        markers = [f"{{{{MCPL_{prefix}_{index}}}}}" for index in range(len(slots) - 1)]
        if any(MARKER.search(slot["value"]) for slot in slots):
            self.diagnostic(node, "原文包含保留的脚本槽位标记")
            return
        source = "".join(slot["value"] + (markers[index] if index < len(markers) else "") for index, slot in enumerate(slots))
        if not any(slot["value"].strip() for slot in slots):
            return
        consumer, owner = node, node.parent
        while owner is not None and owner.type not in FUNCTIONS:
            if owner.type == "call_expression":
                _, method, _ = self.parts(owner)
                if method in MESSAGES | {"add", "addItem", "addFluid", "displayName", "tooltip", "ritualTooltip", "formattedDisplayName", "insert"}:
                    consumer = owner
            owner = owner.parent
        context_expression = self.raw_text(consumer)
        if len(context_expression) > 1200:
            self.diagnostic(node, "显示调用超过上下文上限，需人工处理")
            return
        frozen = shape
        relative_slots = [(slot["start"] - self.char_offset(node.start_byte),
                           slot["end"] - self.char_offset(node.start_byte)) for slot in slots]
        if all(0 <= start <= end <= len(shape) for start, end in relative_slots):
            for start, end in sorted(relative_slots, reverse=True):
                frozen = frozen[:start] + "<text>" + frozen[end:]
        script = {"version": 1, "slots": slots, "markers": markers, "rule": rule, "line": node.start_point.row + 1,
                  "anchor": digest_text(rule + frozen)}
        context = json.dumps({"kind": rule, "expression": context_expression,
                              "slots": [slot["value"] for slot in slots]}, ensure_ascii=False)
        dependencies = set(dependencies)
        owner = node.parent
        while owner is not None and owner.type not in FUNCTIONS:
            if owner.type == "variable_declarator":
                name = owner.child_by_field_name("name")
                if name.type == "identifier" and (binding := self.binding(name)):
                    dependencies.add(binding["id"])
            owner = owner.parent
        self.units.append(Unit(source, script, context, dependencies))

    def scalar_slots(self, node, dependencies, depth=0):
        if depth > 3:
            raise ValueError("变量追踪超过 3 层")
        if node.type == "string":
            return [self.slot(node)]
        if node.type == "template_string":
            substitutions = [child for child in node.named_children if child.type == "template_substitution"]
            boundaries = [(node.start_byte + 1, substitutions[0].start_byte if substitutions else node.end_byte - 1)]
            boundaries.extend((sub.end_byte, substitutions[index + 1].start_byte if index + 1 < len(substitutions)
                               else node.end_byte - 1) for index, sub in enumerate(substitutions))
            return [self.slot(node, start, end, "`") for start, end in boundaries]
        if node.type == "identifier":
            binding = self.binding(node)
            if not binding or not binding["const"] or binding["mutated"] or binding["value"] is None:
                raise ValueError("无法确定变量的不可变文本定义")
            self.allowed_refs.add(node.id)
            dependencies.add(binding["id"])
            return self.scalar_slots(binding["value"], dependencies, depth + 1)
        if node.type == "parenthesized_expression":
            child = next(child for child in node.named_children if child.type != "comment")
            return self.scalar_slots(child, dependencies, depth)
        if node.type == "binary_expression":
            if self.raw_text(node.child_by_field_name("operator")) != "+":
                raise ValueError("只自动处理文字拼接运算")
            slots = []
            for child in (node.child_by_field_name("left"), node.child_by_field_name("right")):
                if child.type in {"string", "template_string", "binary_expression", "parenthesized_expression"}:
                    slots.extend(self.scalar_slots(child, dependencies, depth))
            if not slots:
                raise ValueError("拼接表达式没有明确文字槽位")
            return slots
        raise ValueError("无法确定可安全替换的文本表达式")

    def text_value(self, node, rule, depth=0):
        if depth > 3:
            self.diagnostic(node, "变量或组件追踪超过 3 层")
            return
        if node.type in {"array", "object"}:
            if node.type == "array":
                for child in node.named_children:
                    if child.type != "comment":
                        self.text_value(child, rule, depth + 1)
            else:
                for pair in node.named_children:
                    if pair.type != "pair":
                        continue
                    key = pair.child_by_field_name("key")
                    name = self.raw_text(key).strip("\"'")
                    if name in {"text", "extra", "with", "hover"}:
                        self.text_value(pair.child_by_field_name("value"), rule, depth + 1)
            return
        if node.type == "identifier":
            binding = self.binding(node)
            if binding and binding["const"] and not binding["mutated"] and binding["value"] is not None:
                value = binding["value"]
                if value.type in {"array", "object", "call_expression"}:
                    before = len(self.units)
                    self.allowed_refs.add(node.id)
                    self.text_value(value, rule, depth + 1)
                    for unit in self.units[before:]:
                        unit.dependencies.add(binding["id"])
                    return
        if node.type == "ternary_expression":
            for name in ("consequence", "alternative"):
                self.text_value(node.child_by_field_name(name), rule, depth)
            return
        if node.type == "call_expression":
            obj, method, args = self.parts(node)
            role = self.role(obj)
            if role == "text" and method in FACTORIES and args:
                self.text_value(args[0], rule, depth)
            elif role == "text" and method in {"translate", "translatable", "translateWithFallback", "translatableWithFallback"}:
                if "WithFallback" in method and len(args) > 1:
                    self.text_value(args[1], rule, depth)
                for arg in args[2:] if "WithFallback" in method else args[1:]:
                    if arg.type in {"call_expression", "object", "array"}:
                        self.text_value(arg, rule, depth)
            elif role == "component":
                self.text_value(obj, rule, depth)
                if method == "append" and args:
                    self.text_value(args[0], rule, depth)
            else:
                self.diagnostic(node, "未知函数返回的显示文本")
            return
        try:
            dependencies = set()
            slots = self.scalar_slots(node, dependencies)
            self.emit(node, slots, rule, dependencies)
        except (ValueError, UnicodeError) as exc:
            self.diagnostic(node, str(exc))

    def discover(self):
        # Visit consumers first so factory and outer-sink matches share one unit.
        calls = [node for node in self.nodes if node.type == "call_expression"]
        calls.sort(key=lambda call: self.role(self.parts(call)[0]) == "text")
        for call in calls:
            obj, method, args = self.parts(call)
            role = self.role(obj)
            selected = []
            rule = method
            if role == "text" and method in FACTORIES and args:
                selected = args[:1]
            elif role == "text" and method in {"translate", "translatable", "translateWithFallback", "translatableWithFallback"}:
                self.text_value(call, method)
                continue
            elif role == "builder" and method in {"displayName", "formattedDisplayName", "tooltip", "ritualTooltip"} or role == "component" and method == "append":
                selected = args[:1]
            elif method in MESSAGES and args:
                # Text component arguments are evidence even for Java-native sources.
                if role == "message" or self.role(args[0]) == "component":
                    selected = args[:1]
                else:
                    self.diagnostic(call, "消息方法接收者来源未确认")
            elif role in {"tooltip", "viewer", "jei-old"} and method == "add":
                selected = args[1:2]
            elif role in {"legacy-tooltip", "dynamic-tooltip", "text-builder"} and method == "add":
                selected = args[:1]
            elif role == "modify-tooltip" and method == "add":
                selected = args[2:3] if len(args) == 3 else args[1:2]
            elif role == "tooltip" and method == "addToAll":
                selected = args[:1]
            elif role in {"jei", "rei"} and method in {"addItem", "addFluid"}:
                selected = args[1:3] if role == "rei" else args[1:2]
            elif role in {"jei", "jei-old"} and method == "addForType":
                selected = args[2:3]
            elif role in {"rei", "rei-old"} and method == "add":
                selected = args[2:4] if len(args) == 4 else args[1:3]
            elif role == "lines" and method == "add":
                selected = args[1:2] if len(args) == 2 else args[:1]
            elif role == "text-builder" and method == "insert":
                selected = args[1:2]
            elif method in {"displayName", "tooltip", "ritualTooltip", "add"} and args:
                self.diagnostic(call, "文本用途或事件来源未确认，保留原文")
            for value in selected:
                self.text_value(value, (role + "." + rule))
        unsafe = set()
        for node in self.nodes:
            if node.type != "identifier":
                continue
            binding = self.binding(node)
            if binding and node.id != binding["id"] and node.id not in self.allowed_refs:
                unsafe.add(binding["id"])
        safe = []
        for unit in self.units:
            if unit.dependencies & unsafe:
                self.diagnostics.append({"line": unit.script["line"], "reason": "共享文本变量存在非显示用途或未知用途，保留原文"})
            else:
                safe.append(unit)
        # Avoid overlapping nested matches; a conflict is a diagnostic, not a guessed edit.
        accepted, occupied = [], set()
        for unit in safe:
            spans = {(slot["start"], slot["end"]) for slot in unit.script["slots"]}
            if spans & occupied:
                self.diagnostics.append({"line": unit.script["line"], "reason": "文本定义被不同表达式共享，需人工处理"})
                continue
            occupied.update(spans)
            accepted.append(unit)
        return accepted, self.diagnostics


def discover_script(text):
    return Analyzer(text).discover()


def render_script(text, entries):
    units, _ = discover_script(text)
    available = {tuple((slot["start"], slot["end"]) for slot in unit.script["slots"]): unit for unit in units}
    updates = []
    for entry in entries:
        slots = entry.script.get("slots", [])
        identity = tuple((slot["start"], slot["end"]) for slot in slots)
        unit = available.get(identity)
        if not unit or unit.script != entry.script or unit.source != entry.source:
            raise ValueError("脚本快照的位置、规则或原文与源文件不一致")
        parts = split_translation(entry.source, entry.translation,
                                  manual=entry.status == "reviewed" and entry.origin == "manual")
        for slot, translated in zip(slots, parts, strict=True):
            if text[slot["start"]:slot["end"]] != slot["raw"]:
                raise ValueError("脚本文本槽位不匹配")
            if translated != slot["value"]:
                updates.append((slot["start"], slot["end"], encode_js(translated, slot["quote"])))
    previous, result = len(text) + 1, text
    for start, end, value in sorted(updates, reverse=True):
        if end > previous:
            raise ValueError("脚本文本替换范围重叠")
        result = result[:start] + value + result[end:]
        previous = start
    before, after = parse_script(text), parse_script(result)
    # Leaf kinds/operators/names remain; only approved string contents may differ.
    def shape(node):
        if node.type == "string":
            return ("string",)
        if node.type == "template_string":
            return ("template_string", tuple(shape(child) for child in node.named_children
                                             if child.type == "template_substitution"))
        return (node.type, tuple(shape(child) for child in node.children))
    if shape(before.root_node) != shape(after.root_node):
        raise ValueError("译文改变了 JavaScript 语法结构")
    return result


def digest_text(value):
    return hashlib.sha256(value.encode()).hexdigest()[:16]
