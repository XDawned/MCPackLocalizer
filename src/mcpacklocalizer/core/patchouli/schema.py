"""Known visible fields and static template variable use analysis."""
import re

from ..formats.documents import String
from .text import VARIABLE

PAGE_FIELDS = {
    "text": ("title", "text"), "image": ("title", "text"),
    "crafting": ("title", "text"), "smelting": ("title", "text"),
    "multiblock": ("name", "text"), "entity": ("name", "text"),
    "spotlight": ("title", "text"), "link": ("title", "text", "link_text"),
    "relations": ("title", "text"), "quest": ("title", "text"), "empty": (),
}
TEXT_FUNCTIONS = {"upper", "lower", "trim", "capital", "fcapital"}


def value(node, default=""):
    return node.value if isinstance(node, String) else default


def namespaced(identifier, namespace):
    return identifier if ":" in identifier else namespace + ":" + identifier


def fields(node, allowed, path=()):
    if isinstance(node, dict):
        for name in allowed:
            if isinstance(node.get(name), String):
                yield path + (name,), node[name]


def variable_uses(text):
    for match in VARIABLE.finditer(text):
        expression = match.group().strip("#").split("->")
        yield expression[0], expression[1:]


class Templates:
    def __init__(self, nodes, namespace, warn):
        self.nodes, self.namespace, self.warn = nodes, namespace, warn
        self.cache = {}

    def analyze(self, identifier, stack=()):
        """Return variable roles and literal JSON paths; never execute processors."""
        identifier = namespaced(identifier, self.namespace)
        if identifier in self.cache:
            return self.cache[identifier]
        if identifier in stack:
            raise ValueError(f"帕秋莉模板循环引用：{identifier}")
        node = self.nodes.get(identifier)
        if node is None:
            raise ValueError(f"未知的帕秋莉页面/模板：{identifier}")
        if not isinstance(node, dict):
            raise TypeError(f"无效的帕秋莉模板：{identifier}")
        roles, literals = {}, []

        def use(text, role, path):
            uses = list(variable_uses(text.value))
            for name, functions in uses:
                actual = role if all(f in TEXT_FUNCTIONS for f in functions) else "structural"
                roles.setdefault(name, set()).add(actual)
            if role == "text" and (not uses or not re.fullmatch(VARIABLE.pattern, text.value)):
                literals.append(path)

        for index, component in enumerate(node.get("components", [])):
            if not isinstance(component, dict):
                continue
            kind = value(component.get("type")).removeprefix("patchouli:")
            if kind not in {"text", "header", "tooltip", "item", "image", "entity", "separator", "frame"}:
                self.warn(f"{identifier} 中存在未知的帕秋莉组件：{kind}")
                continue
            for name, string in component.items():
                role = "text" if name == "text" and kind in {"text", "header"} else "structural"
                path = ("components", index, name)
                if isinstance(string, String):
                    use(string, role, path)
                elif name == "tooltip" and kind == "tooltip" and isinstance(string, list):
                    for line, item in enumerate(string):
                        if isinstance(item, String):
                            use(item, "text", path + (line,))
        for index, include in enumerate(node.get("include", [])):
            if not isinstance(include, dict):
                continue
            child = value(include.get("template"))
            prefix = value(include.get("as"))
            if not child or not prefix:
                raise ValueError(f"帕秋莉引用必须同时提供 template 和非空 as：{identifier}")
            child_roles, _ = self.analyze(child, (*stack, identifier))
            bindings = include.get("using", {})
            if not isinstance(bindings, dict):
                raise TypeError(f"无效的模板绑定：{identifier}")
            for name, child_use in child_roles.items():
                binding = bindings.get(name)
                if isinstance(binding, String):
                    for role in child_use:
                        use(binding, role, ("include", index, "using", name))
                elif binding is None:
                    roles.setdefault(prefix + "." + name, set()).update(child_use)
        if value(node.get("processor")):
            self.warn(f"帕秋莉处理器变量需要适配器：{identifier}")
            roles = {name: {"structural"} for name in roles}
        result = roles, list(dict.fromkeys(literals))
        self.cache[identifier] = result
        return result

    def page_fields(self, page, path):
        kind = value(page.get("type"), "patchouli:text")
        if kind.startswith("patchouli:") or ":" not in kind and kind in PAGE_FIELDS:
            builtin = kind.removeprefix("patchouli:")
            if builtin not in PAGE_FIELDS:
                raise ValueError(f"未知的帕秋莉页面：{kind}")
            yield from fields(page, PAGE_FIELDS[builtin], path)
            return
        roles, _ = self.analyze(kind)
        for name, usage in roles.items():
            if usage == {"text"}:
                yield from fields(page, (name,), path)
            elif "text" in usage:
                self.warn(f"帕秋莉变量同时控制非文本数据；已保留：{kind}:{name}")


def get(node, path):
    for part in path:
        node = node[part]
    return node
