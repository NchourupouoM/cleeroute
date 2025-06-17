from typing import List, Optional
from pydantic import BaseModel

# ================================ video search ==========

class VideoSearch(BaseModel):
    title: str
    category: str
    section: str
    subsection: str

    class Config:
        json_schema_extra = {
                "example": {
                    "title":"Deep Learning for Computer Vision",#Achieving Native-Like English Fluency",
                    "category":"Deep Learning",#English Language Learning",
                    "section":"Convolutional Neural Networks",#Mastering English Phonetics and Sounds",
                    "subsection":"Backpropagation in convnets",#Individual Vowel Sounds"
                }
            }

class VideoResponse(BaseModel):
    title: str
    url: str
    thumbnail: str
    duration: str

    class Config:
        from_attributes = True

class PaginatedVideoResponse(BaseModel):
    items: List[VideoResponse]
    total_items: int
    total_pages: int
    current_page: int
    page_size: int