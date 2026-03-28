"""Generate the container stack diagram used in the README."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


WIDTH = 248
HEIGHT = 440
OUTPUT = Path(__file__).with_name("container_stack.png")

TITLE_FONT = "/System/Library/Fonts/Supplemental/Trebuchet MS Bold.ttf"
BOLD_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
BODY_FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"


def vertical_gradient(size, top, bottom):
    """Create a vertical RGBA gradient."""
    width, height = size
    image = Image.new("RGBA", size, 0)
    pixels = image.load()
    for y in range(height):
        blend = y / max(height - 1, 1)
        color = tuple(int(top[i] * (1 - blend) + bottom[i] * blend) for i in range(4))
        for x in range(width):
            pixels[x, y] = color
    return image


def rounded_panel(size, radius, fill_top, fill_bottom, stroke=None, stroke_width=0):
    """Create a rounded rectangle panel with a vertical gradient fill."""
    panel = Image.new("RGBA", size, (0, 0, 0, 0))
    gradient = vertical_gradient(size, fill_top, fill_bottom)
    mask = Image.new("L", size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    panel.paste(gradient, (0, 0), mask)
    if stroke and stroke_width:
        panel_draw = ImageDraw.Draw(panel)
        for index in range(stroke_width):
            panel_draw.rounded_rectangle(
                (index, index, size[0] - 1 - index, size[1] - 1 - index),
                radius=radius,
                outline=stroke,
            )
    return panel


def add_shadow(base, box, radius=10, offset=(0, 6), color=(24, 45, 74, 70)):
    """Add a soft shadow behind a rounded rectangle."""
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    x0, y0, x1, y1 = box
    x_offset, y_offset = offset
    shadow_draw.rounded_rectangle(
        (x0 + x_offset, y0 + y_offset, x1 + x_offset, y1 + y_offset),
        radius=radius,
        fill=color,
    )
    base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(8)))


def build_diagram():
    """Create the Nautobot container stack image."""
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    image.alpha_composite(vertical_gradient((WIDTH, HEIGHT), (241, 247, 252, 255), (220, 234, 245, 255)))

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for y in range(42, HEIGHT, 28):
        overlay_draw.line((18, y, WIDTH - 18, y), fill=(255, 255, 255, 34), width=1)
    for x in range(28, WIDTH, 32):
        overlay_draw.line((x, 42, x, HEIGHT - 22), fill=(255, 255, 255, 18), width=1)
    image.alpha_composite(overlay)

    title_font = ImageFont.truetype(TITLE_FONT, 18)
    label_font = ImageFont.truetype(BOLD_FONT, 11)
    box_font = ImageFont.truetype(BOLD_FONT, 15)
    box_font_small = ImageFont.truetype(BOLD_FONT, 13)
    mini_font = ImageFont.truetype(BODY_FONT, 9)

    draw = ImageDraw.Draw(image)
    draw.text((WIDTH // 2, 18), "Container Stack", anchor="mm", font=title_font, fill=(38, 68, 94, 255))
    draw.text((WIDTH // 2, 34), "Nautobot 3", anchor="mm", font=mini_font, fill=(83, 115, 140, 255))

    vm_box = (23, 49, 225, 410)
    add_shadow(image, vm_box, radius=16, offset=(0, 8), color=(28, 52, 79, 58))
    vm_panel = rounded_panel(
        (vm_box[2] - vm_box[0], vm_box[3] - vm_box[1]),
        16,
        (247, 251, 254, 255),
        (233, 241, 247, 255),
        stroke=(107, 128, 145, 255),
        stroke_width=3,
    )
    image.alpha_composite(vm_panel, vm_box[:2])

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((39, 61, 209, 84), radius=10, fill=(226, 235, 242, 255))
    draw.text((124, 72), "VIRTUAL MACHINE", anchor="mm", font=label_font, fill=(81, 102, 116, 255))

    containers = [
        ("Nautobot App", "Web UI + API", (89, 208, 176, 255), (62, 170, 140, 255), (20, 58, 66, 255), box_font),
        ("Celery Worker", "Async jobs", (247, 197, 104, 255), (228, 167, 62, 255), (78, 50, 0, 255), box_font),
        ("Celery Beat", "Scheduled tasks", (248, 221, 116, 255), (226, 187, 53, 255), (92, 71, 0, 255), box_font),
        ("Redis", "Broker + cache", (248, 120, 110, 255), (219, 87, 80, 255), (255, 248, 248, 255), box_font),
        (
            "PostgreSQL / MySQL",
            "Database",
            (131, 170, 245, 255),
            (84, 118, 212, 255),
            (248, 251, 255, 255),
            box_font_small,
        ),
    ]

    box_left = 46
    box_right = 202
    box_width = box_right - box_left
    box_height = 42
    start_y = 98
    gap = 12

    for index, (title, subtitle, top_color, bottom_color, text_color, font) in enumerate(containers):
        top = start_y + index * (box_height + gap)
        bottom = top + box_height
        add_shadow(image, (box_left, top, box_right, bottom), radius=11, offset=(0, 4), color=(18, 36, 58, 48))
        panel = rounded_panel(
            (box_width, box_height),
            11,
            top_color,
            bottom_color,
            stroke=(255, 255, 255, 70),
            stroke_width=1,
        )
        image.alpha_composite(panel, (box_left, top))

        draw = ImageDraw.Draw(image)
        draw.text((124, top + 15), title, anchor="mm", font=font, fill=text_color)
        subtitle_color = text_color if index < 3 else (255, 243, 243, 230) if index == 3 else (240, 245, 255, 230)
        draw.text((124, top + 29), subtitle, anchor="mm", font=mini_font, fill=subtitle_color)
        if index < len(containers) - 1:
            arrow_top = bottom + 3
            arrow_bottom = bottom + gap - 3
            draw.rounded_rectangle((122, arrow_top, 126, arrow_bottom), radius=2, fill=(122, 142, 158, 220))
            draw.polygon([(119, arrow_bottom - 1), (129, arrow_bottom - 1), (124, arrow_bottom + 6)], fill=(122, 142, 158, 220))

    whale = Image.new("RGBA", (90, 40), (0, 0, 0, 0))
    whale_draw = ImageDraw.Draw(whale)
    whale_draw.rounded_rectangle((10, 12, 66, 32), radius=10, fill=(79, 116, 205, 255))
    whale_draw.polygon([(66, 17), (88, 22), (66, 29)], fill=(79, 116, 205, 255))
    for x in (28, 38, 48):
        whale_draw.rectangle((x, 4, x + 7, 12), fill=(102, 139, 224, 255))
    whale_draw.ellipse((52, 19, 56, 23), fill=(255, 255, 255, 255))
    image.alpha_composite(whale.filter(ImageFilter.GaussianBlur(0.2)), (79, 360))

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((57, 425, 191, 431), radius=3, fill=(193, 207, 218, 150))
    return image


if __name__ == "__main__":
    build_diagram().save(OUTPUT)
