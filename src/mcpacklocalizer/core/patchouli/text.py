"""Protect Patchouli controls, template expressions and book-specific macros."""
import re

VARIABLE = re.compile(r"#[A-Za-z_][\w.]*(?:->[A-Za-z_][\w]*)*#?")
CONTROL = re.compile(r"\$\([^)]*\)|#[A-Za-z_][\w.]*(?:->[A-Za-z_][\w]*)*#?")
TOOLTIP = re.compile(r"\$\(t:([^)]*)\)")


def pattern(macros=()):
    literals = [re.escape(m) for m in sorted(set(macros), key=len, reverse=True) if m]
    return re.compile("|".join([*literals, CONTROL.pattern]))


def validate_text(source, translated, macros=()):
    controls = pattern(macros)
    if controls.findall(source) != controls.findall(translated):
        raise ValueError("译文修改了帕秋莉格式、链接、命令、宏或模板变量")


def translate_text(model, source, context, macros=()):
    """Keep syntax outside model output; existing translation engines handle prose."""
    prefix = "MCPL_PATCHOULI_"
    while prefix in source:
        prefix += "X"
    mapping = {}

    def mask(match):
        marker = "{{" + prefix + str(len(mapping)) + "}}"
        mapping[marker] = match.group()
        return marker

    masked = pattern(macros).sub(mask, source)
    translated = model.translate(masked, context)
    if any(translated.count(marker) != 1 for marker in mapping):
        raise ValueError("帕秋莉保留符丢失或重复")
    if mapping:
        translated = re.sub("|".join(map(re.escape, mapping)), lambda m: mapping[m.group()], translated)
    # The engine also validates general ID/printf/color syntax in its normal path.
    validate_text(source, translated, macros)
    return translated
