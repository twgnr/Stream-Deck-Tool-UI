#--------------------------------------------------------------------
# Import packages
#--------------------------------------------------------------------
import os
import matplotlib.font_manager as fm

#--------------------------------------------------------------------
# Import sub-packages
#--------------------------------------------------------------------
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.ImageHelpers import PILHelper

#--------------------------------------------------------------------
# Import local packages
#--------------------------------------------------------------------
from config_manager import log


# A new helper function to draw a border inside an image.
def draw_active_border(draw, size, color="#28A745", width=4):
    """Draws a rectangle border inside the given image dimensions."""
    draw.rectangle(((0, 0), (size[0] - 1, size[1] - 1)), outline=color, width=width)


def render_error_key(deck, text="ERROR"):
    """Creates a standardized red error image for a key."""
    image_format = deck.key_image_format()
    image = Image.new("RGB", image_format['size'], "maroon")
    draw = ImageDraw.Draw(image)

    icon_path = os.path.join("icons", "error.png")
    try:
        icon = Image.open(icon_path).convert("RGBA")
        icon.thumbnail((image_format['size'][0] - 20, image_format['size'][1] - 20))
        icon_pos = ((image_format['size'][0] - icon.width) // 2, 5)
        image.paste(icon, icon_pos, icon)
    except Exception:
        # Fallback to just text if icon is missing
        pass

    try:
        font_path = "C:/Windows/Fonts/Arial.ttf" # Using a known font for fallback
        font = ImageFont.truetype(font_path, 14)
        label_pos = (image_format['size'][0] // 2, image_format['size'][1] - 5)
        draw.text(label_pos, text=text, font=font, anchor="ms", fill="white")
    except IOError:
        label_pos = (image_format['size'][0] // 2, image_format['size'][1] - 5)
        draw.text(label_pos, text=text, anchor="ms", fill="white")

    return PILHelper.to_native_format(deck, image)


def render_key_image(deck, icon_name, label_text, icon_folder, global_font_path, font_size=14, label_pos_config="bottom", font_color="white", font_settings=None, background_color="#000000", is_layer_key=False, is_active_toggle=False):
    """Creates a Pillow Image object for a key, using paths provided as arguments."""
    image_format = deck.key_image_format()
    image = Image.new("RGB", image_format['size'], background_color)
    draw = ImageDraw.Draw(image)

    # Draw Icon
    if icon_name:
        icon_path = os.path.join(icon_folder, icon_name)
        try:
            icon = Image.open(icon_path).convert("RGBA")
            icon_size = image_format['size']
            icon.thumbnail(icon_size)
            icon_pos = ((image_format['size'][0] - icon.width) // 2, (image_format['size'][1] - icon.height) // 2)
            image.paste(icon, icon_pos, icon)
        except Exception as e:
            log.warning(f"Could not load icon '{icon_path}': {e}")

    # Draw Label
    if label_text:
        font_to_use = None
        final_font_size = font_size
        
        if font_settings:
            final_font_size = font_settings.get("size", font_size)
            font_family = font_settings.get("family")
            font_path = font_settings.get("path")
            
            try:
                if font_path:
                    font_to_use = ImageFont.truetype(font_path, final_font_size)
                elif font_family:
                    font_file = fm.findfont(fm.FontProperties(family=font_family))
                    font_to_use = ImageFont.truetype(font_file, final_font_size)
            except Exception as e:
                log.warning(f"Warning: Could not load custom font '{font_family or font_path}'. Error: {e}")

        # Fallback to global font if no custom font was loaded
        if not font_to_use:
            try:
                font_to_use = ImageFont.truetype(global_font_path, final_font_size)
            except IOError:
                log.warning(f"Warning: Global font not found at '{global_font_path}'. Using default.")
                font_to_use = ImageFont.load_default()

        try:
            w, h = image_format['size']

            if '\n' in label_text:
                # Calculate the bounding box to get the total width and height of the text block.
                bbox = draw.multiline_textbbox((0, 0), text=label_text, font=font_to_use, align="center")
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

                # Determine the top-left (x, y) coordinate based on the desired position.
                x = (w - text_width) / 2
                if label_pos_config == "top":
                    y = 5  # 5px margin from top
                elif label_pos_config == "middle":
                    y = (h - text_height) / 2
                else:  # Default to bottom
                    y = h - text_height - 5  # 5px margin from bottom
                
                label_pos = (x, y)
                
                # Draw the multiline text at the calculated position.
                draw.multiline_text(label_pos, text=label_text, font=font_to_use, fill=font_color, align="center", stroke_width=1, stroke_fill="black")
           
            # For single-line text, this anchor method is simpler
            else:
                if label_pos_config == "top":
                    label_pos = (w // 2, 5)
                    anchor = "mt"  # Middle Top
                elif label_pos_config == "middle":
                    label_pos = (w // 2, h // 2)
                    anchor = "mm"  # Middle Middle
                else:  # Default to "bottom"
                    label_pos = (w // 2, h - 5)
                    anchor = "ms"  # Middle Bottom
                
                draw.text(label_pos, text=label_text, font=font_to_use, anchor=anchor, fill=font_color, stroke_width=1, stroke_fill="black")
        except Exception as e:
            log.warning(f"Error drawing text: {e}")
            # Fallback for any drawing error
            draw.text((w // 2, h - 5), text="TXT_ERR", anchor="ms", fill="red")

    if is_layer_key:
        size = image_format['size']
        corner_size = int(size[0] * 0.2)
        p1 = (size[0] - corner_size, 0)
        p2 = (size[0], 0)
        p3 = (size[0], corner_size)
        draw.polygon([p1, p2, p3], fill="#FFD700")
        draw.line([(size[0] - corner_size, 0), (size[0], corner_size)], fill=(0, 0, 0, 77), width=1)

    if is_active_toggle:
        draw_active_border(draw, image_format['size'])
        
    return PILHelper.to_native_format(deck, image)


def get_blank_key_image(deck):
    """Creates a blank black image for a key."""
    image_format = deck.key_image_format()
    blank_image = Image.new("RGB", image_format['size'], "black")
    return PILHelper.to_native_format(deck, blank_image)