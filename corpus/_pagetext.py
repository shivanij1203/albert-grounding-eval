import re, html, sys
def page_text(raw: str) -> str:
    raw = re.sub(r"<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", " ", raw, flags=re.S)
    raw = re.sub(r"</(p|li|h[1-6]|div|tr)>|<br\s*/?>", "\n", raw)
    t = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in t.split("\n")]
    return "\n".join(l for l in lines if l)
if __name__ == "__main__":
    print(page_text(open(sys.argv[1], errors="ignore").read()))
