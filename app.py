from fastapi import FastAPI, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv
import os

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST","GET","OPTIONS"],
    allow_headers=["*"],
)

# MongoDB client setup
load_dotenv()

# Get the MongoDB URI from the environment
mongodb_uri = os.getenv("MONGODB_URI")

# Use the MongoDB URI to initialize the client
client = AsyncIOMotorClient(mongodb_uri)
db = client["hotel_database"]
collection = db["hotels"]

# Pydantic models for structuring the response
class OTAInfo(BaseModel):
    provider: str
    bdt_price: float
    usd_price: float
    redirect: Optional[str] = None

class BestPrice(BaseModel):
    provider: str
    bdt_price: float
    usd_price: float
    redirect: Optional[str] = None  # Add redirect to the best price

class HotelInfo(BaseModel):
    name: str
    image: str
    prices: List[OTAInfo]
    bestPrice: BestPrice

class SearchFilters(BaseModel):
    place: str
    adults: int
    rooms: int
    budget: Optional[str] = None  # Assuming budget is a string like '0-5000'

class SearchResponse(BaseModel):
    hotels: List[HotelInfo]  # Changed to match the actual hotel info being returned
@app.get("/health")
async def health_check():
    return {"status": "OK", "message": "Server is running!"}

@app.post("/hotels", response_model=SearchResponse)
async def search_hotels(filters: SearchFilters = Body(...)):
    # Convert budget to range
    budget_range = None
    if filters.budget:
        min_budget, max_budget = map(float, filters.budget.split('-'))
        budget_range = (min_budget, max_budget)
    
    # Define the query based on the provided search filters
    query = {
        "Place": filters.place,
        "Adult_Person": filters.adults,
        "Room_Count": filters.rooms,
    }

    # Add budget constraint if provided (BDT price)
    if budget_range is not None:
        query["BDT_Price"] = {"$gte": budget_range[0], "$lte": budget_range[1]}

    # Fetch data from MongoDB
    hotels_cursor = collection.find(query)
    hotels = await hotels_cursor.to_list(length=100)  # Fetch a max of 100 results

    # Dictionary to store merged hotel information by name
    merged_hotels = {}

    for hotel in hotels:
        # Extract hotel data
        hotel_name = hotel.get("Hotel_Name", "Unknown Hotel")
        image_link = hotel.get("Image_Link", "")
        redirect_link = hotel.get("Redirect_Link", "Unknown Link")
        bdt_price = float(hotel.get("BDT_Price", 0))
        usd_price = float(hotel.get("USD_Price", 0))
        provider = hotel.get("OTA", "Unknown Provider")

        ota_info = {
            "provider": provider,
            "bdt_price": bdt_price,
            "usd_price": usd_price,
            "redirect": redirect_link
        }

        # Check if the hotel is already in the dictionary
        if hotel_name in merged_hotels:
            # Append the OTA price information
            merged_hotels[hotel_name]["prices"].append(ota_info)

            # Compare the existing best price with the current price and update if better
            existing_best_price = merged_hotels[hotel_name]["bestPrice"]
            if bdt_price < existing_best_price["bdt_price"]:
                # Update the best price, including the redirect link
                merged_hotels[hotel_name]["bestPrice"] = {
                    "provider": provider,
                    "bdt_price": bdt_price,
                    "usd_price": usd_price,
                    "redirect": redirect_link  # Include the redirect link of the best price
                }
        else:
            # Add a new hotel entry with the OTA price information
            merged_hotels[hotel_name] = {
                "name": hotel_name,
                "image": image_link,
                "prices": [ota_info],  # Initialize with the current OTA info
                "bestPrice": {
                    "provider": provider,
                    "bdt_price": bdt_price,
                    "usd_price": usd_price,
                    "redirect": redirect_link  # Include redirect link in best price
                }
            }

    # Convert merged hotels back to a list
    formatted_hotels = list(merged_hotels.values())

    return {"hotels": formatted_hotels}
