"""產生一張合成的台電風格電費單測試圖(所有資料皆為虛構,避免 demo 使用真實個資)。
用法: python make_sample_bill.py  → 輸出 sample_bill.png
"""
from PIL import Image, ImageDraw, ImageFont

CJK_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "C:/Windows/Fonts/msjh.ttc",            # Windows 微軟正黑
    "/System/Library/Fonts/PingFang.ttc",   # macOS
]


def load_font(size):
    for p in CJK_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


W, H = 900, 620
img = Image.new("RGB", (W, H), "#f7f6f2")
d = ImageDraw.Draw(img)

f_title = load_font(30)
f_label = load_font(20)
f_value = load_font(24)
f_big = load_font(40)
f_small = load_font(15)

d.rectangle([0, 0, W, 78], fill="#1a4f8b")
d.text((30, 20), "台灣電力公司  電費通知單(範本/測試用)", font=f_title, fill="white")

rows = [
    ("用電種類", "高壓電力(工業用)"),
    ("電號", "07-51-2088-13-6"),
    ("計費期間", "115年04月01日 至 115年05月31日"),
    ("用電度數", "42,580 度"),
    ("流動電費", "121,390 元"),
]
y = 110
for label, value in rows:
    d.text((40, y), label, font=f_label, fill="#666")
    d.text((230, y - 4), value, font=f_value, fill="#111")
    d.line([40, y + 40, W - 40, y + 40], fill="#ddd", width=1)
    y += 62

d.rectangle([40, y + 10, W - 40, y + 110], outline="#1a4f8b", width=2)
d.text((60, y + 28), "本期應繳總金額", font=f_label, fill="#1a4f8b")
d.text((60, y + 54), "NT$ 128,460", font=f_big, fill="#c0392b")
d.text((40, H - 36), "※ 本圖為系統測試合成範本,非真實帳單。電號與金額皆為虛構。", font=f_small, fill="#999")

img.save("sample_bill.png")
print("已產生 sample_bill.png")
