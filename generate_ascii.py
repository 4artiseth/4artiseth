from PIL import Image
import sys

def image_to_ascii(image_path, width=40, height=26):
    """Convert image to ASCII art"""
    # ASCII characters matching the reference image (darkest to lightest)
    ascii_chars = ['&', '$', 'X', 'x', '+', ';', ':', '.']
    
    # Open image
    img = Image.open(image_path)
    
    # Crop to capture face with better framing
    w, h = img.size
    # Adjusted crop for better facial features
    left = int(w * 0.22)
    right = int(w * 0.78)
    top = int(h * 0.08)
    bottom = int(h * 0.70)
    img = img.crop((left, top, right, bottom))
    
    # Calculate aspect ratio (adjust to prevent squishing)
    aspect_ratio = img.height / img.width
    new_height = int(width * aspect_ratio * 0.48)  # Adjusted ratio
    
    # Adjust to fit our constraints
    if new_height > height:
        new_height = height
        width = int(height / aspect_ratio / 0.48)
    
    img = img.resize((width, new_height))
    img = img.convert('L')  # Convert to grayscale
    
    # Apply slight blur to reduce noise
    from PIL import ImageFilter
    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    
    # Fine-tune for better facial features with limited character set
    from PIL import ImageEnhance
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)  # Moderate contrast
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.0)  # Neutral brightness
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(1.0)  # Neutral sharpness
    
    # Convert pixels to ASCII
    ascii_art = []
    pixels = list(img.getdata())
    
    for i in range(0, len(pixels), width):
        row = pixels[i:i+width]
        # Map each pixel to ASCII character with extended character set
        ascii_row = ''.join([ascii_chars[min(pixel * len(ascii_chars) // 256, len(ascii_chars) - 1)] for pixel in row])
        ascii_art.append(ascii_row)
    
    # Pad to 26 lines
    while len(ascii_art) < 26:
        ascii_art.append(' ' * 40)
    
    return ascii_art[:26]

if __name__ == '__main__':
    # You'll need to provide the image path
    print("Please save your profile photo as 'profile.jpg' in this directory")
    print("Then run: python generate_ascii.py")
    
    try:
        ascii_lines = image_to_ascii('profile.jpg', width=40, height=26)
        
        print("\nGenerated ASCII Art:")
        print("=" * 40)
        for line in ascii_lines:
            print(line)
        print("=" * 40)
        
        # Save to file
        with open('ascii_output.txt', 'w') as f:
            for line in ascii_lines:
                f.write(line + '\n')
        
        print("\nSaved to ascii_output.txt")
        
    except FileNotFoundError:
        print("\nError: profile.jpg not found!")
        print("Please save your profile photo as 'profile.jpg' first")
