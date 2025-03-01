import requests
from PIL import Image
from io import BytesIO
import os
from sqlalchemy.orm import Session
from models import Product, SessionLocal

def validate_csv(df):
    # Check if required columns exist
    required_columns = ["S. No.", "Product Name", "Input Image Urls"]
    if not all(column in df.columns for column in required_columns):
        raise ValueError("CSV is missing required columns.")
    return True

def process_image(url, save_dir="images/processed"):
    try:
        # Download the image
        response = requests.get(url)
        if response.status_code != 200:
            raise ValueError(f"Failed to download image from {url}")
        
        # Open the image and compress it
        image = Image.open(BytesIO(response.content))
        image = image.resize((image.width // 2, image.height // 2))  # Resize to 50%
        
        # Save the compressed image to the local server
        os.makedirs(save_dir, exist_ok=True)  # Create the directory if it doesn't exist
        filename = os.path.basename(url)  # Extract the filename from the URL
        processed_image_path = os.path.join(save_dir, f"processed_{filename}")
        image.save(processed_image_path, format="JPEG", quality=50)
        
        # Return the URL of the processed image
        return f"http://localhost:8001/processed/{os.path.basename(processed_image_path)}"
    except Exception as e:
        raise ValueError(f"Error processing image {url}: {e}")

def save_to_db(serial_number, product_name, input_urls, output_urls, db: Session):
    # Check if a product with the same serial_number already exists
    existing_product = db.query(Product).filter(Product.serial_number == serial_number).first()
    
    if existing_product:
        # Update the existing product
        existing_product.product_name = product_name
        existing_product.input_image_urls = input_urls
        existing_product.output_image_urls = output_urls
        existing_product.processed = True
    else:
        # Insert a new product
        product = Product(
            serial_number=serial_number,
            product_name=product_name,
            input_image_urls=input_urls,
            output_image_urls=output_urls,
            processed=True
        )
        db.add(product)
    
    # Commit the changes
    db.commit()