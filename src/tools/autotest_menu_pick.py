"""Pure logic for engine-mode (UE4SS UMG) menu navigation, importable and testable offline.

A menu step's engine label has the forms "text", "name:Widget" or "name:Widget@Screen" (Screen must occur in the widget path: the same
button name exists on several screens, e.g. ContinueBtn on HealthWarning / PressStart / Logos).
A button dict comes from a Lua 'BTN class= name= label= enabled= rooted= path=' log line (only buttons whose own and all ancestors'
visibility is true and whose WidgetSwitcher branches are active are listed by the Lua side).

Offline check:  python autotest_menu_pick.py <UE4SS.log or widgets dump> ...  (prints which step would be picked for each BTN block)
"""
import re
import sys

DENY_NAMES = {"RemoveButton", "ConfirmRed", "RenameButton", "UploadButton", "ConvertButton", "UpgradeButton", "ImportSaveButton"}


def parse_label(label):
    """-> (by_name, text, under)"""
    under = None
    m = re.match(r"^(.*?)@(\S+)$", label)
    if m:
        label, under = m.group(1), m.group(2)
    by_name = label.startswith("name:")
    return by_name, (label[5:] if by_name else label), under


def btn_matches(b, label):
    by_name, text, under = parse_label(label)
    field = b.get("name", "") if by_name else b.get("label", "")
    if text.lower() not in field.lower():
        return False
    if under and under.lower() not in b.get("path", "").lower():
        return False
    return True


def denied(b):
    lb = b.get("label", "").lower()
    return b.get("name", "") in DENY_NAMES or "remove" in lb or "delete" in lb


def candidates(todo, last_k):
    """step indices that may be acted on next: the last acted step (retry) and the next steps, skipping only over steps marked 'skippable'
    (a screen that is not shown in every launch, e.g. the title 'press start'). A later, non-adjacent step is never allowed, so a
    mis-reported visible button of a far-away screen (e.g. the final 'StartButton') cannot jump the chain."""
    out = []
    if last_k >= 0:
        out.append(last_k)
    j = last_k + 1
    while j < len(todo):
        out.append(j)
        if not todo[j].get("skippable"):
            break
        j += 1
    return out


def pick(todo, btns, last_k):
    """-> (step index, button) of the highest allowed step whose key button is visible, else (None, None)"""
    for k in reversed(candidates(todo, last_k)):
        eng = todo[k].get("engine") or {}
        label = eng.get("label")
        if not label:
            continue
        for b in btns:
            if btn_matches(b, label) and not denied(b):
                return k, b
    return None, None


def parse_btn_lines(text):
    res = []
    for m in re.finditer(r"BTN ([^\r\n]*)", text):
        kv = dict((k, v) for k, v in re.findall(r"(\w+)=(.*?)(?= \w+=|$)", m.group(1)))
        res.append(kv)
    return res


if __name__ == "__main__":
    import json
    import os
    menus = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mods", "SN2AutoTest", "plans", "menus.json")))
    for chain in ("new_game", "quit_game"):
        todo = [s for s in menus[chain] if s.get("engine")]
        for path in sys.argv[1:]:
            btns = parse_btn_lines(open(path, errors="replace").read())
            for last_k in range(-1, len(todo)):
                k, b = pick(todo, btns, last_k)
                print("%s %s last_k=%d -> %s" % (chain, os.path.basename(path), last_k, (todo[k]["screen"], b.get("name")) if b else None))
