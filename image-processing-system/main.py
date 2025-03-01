from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
import pandas as pd
import uuid
from io import StringIO
from sqlalchemy.orm import Session
from image-processing-system.models import Product, SessionLocal
from image-processing-system.utils import validate_csv, process_image, save_to_db
import subprocess
import atexit
import os
import requests

app = FastAPI()

# Dictionary to store request statuses
request_statuses = {}

# Start the local image server (only for local development)
if os.getenv("ENV") != "production":
    server_process = subprocess.Popen(["python", "-m", "http.server", "8001", "--directory", "images"])
    # Ensure the server is stopped when the application exits
    atexit.register(server_process.terminate)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/upload/")
async def upload_csv(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    # Read the CSV file
    content = await file.read()
    df = pd.read_csv(StringIO(content.decode('utf-8')))
    
    # Validate the CSV
    try:
        validate_csv(df)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Generate a unique request ID
    request_id = str(uuid.uuid4())
    
    # Initialize the request status
    request_statuses[request_id] = {"status": "Processing", "output_csv_path": None}
    
    # Start background task to process images
    background_tasks.add_task(process_images, df, request_id)
    
    return {"request_id": request_id}

async def process_images(df, request_id):
    db = SessionLocal()
    try:
        # Create a list to store output data
        output_data = []
        
        for index, row in df.iterrows():
            serial_number = row["S. No."]
            product_name = row["Product Name"]
            input_urls = row["Input Image Urls"].split(",")
            output_urls = []
            
            # Process each image URL
            for url in input_urls:
                try:
                    # Process the image and get the URL of the processed image
                    processed_image_url = process_image(url.strip())
                    output_urls.append(processed_image_url)
                except Exception as e:
                    print(f"Failed to process image {url}: {e}")
                    output_urls.append("")  # Skip invalid URLs
            
            # Save the data to the database
            save_to_db(serial_number, product_name, ",".join(input_urls), ",".join(output_urls), db)
            
            # Append the row to the output data
            output_data.append({
                "S. No.": serial_number,
                "Product Name": product_name,
                "Input Image Urls": ",".join(input_urls),
                "Output Image Urls": ",".join(output_urls)
            })
        
        # Generate the output CSV file
        os.makedirs("outputs", exist_ok=True)  # Create the outputs folder
        output_csv_path = f"outputs/output_{request_id}.csv"
        output_df = pd.DataFrame(output_data)
        output_df.to_csv(output_csv_path, index=False)
        
        # Update the request status
        request_statuses[request_id] = {"status": "Completed", "output_csv_path": output_csv_path}
        
        # Trigger the webhook
        webhook_url = os.getenv("WEBHOOK_URL", "http://example.com/webhook")  # Use environment variable for webhook URL
        webhook_data = {
            "request_id": request_id,
            "status": "Completed",
            "output_csv_path": output_csv_path
        }
        try:
            requests.post(webhook_url, json=webhook_data)
        except Exception as e:
            print(f"Failed to trigger webhook: {e}")
        
        print(f"Output CSV file generated: {output_csv_path}")
    finally:
        db.close()

@app.get("/status/{request_id}")
async def get_status(request_id: str):
    # Check if the request ID exists
    if request_id not in request_statuses:
        raise HTTPException(status_code=404, detail="Request ID not found")
    
    # Return the status and output CSV path
    return {
        "request_id": request_id,
        "status": request_statuses[request_id]["status"],
        "output_csv_path": request_statuses[request_id]["output_csv_path"]
    }

@app.post("/webhook/")
async def webhook(data: dict):
    # Handle webhook data
    print(f"Webhook received: {data}")
    return {"status": "Webhook received"}