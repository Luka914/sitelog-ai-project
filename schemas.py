from typing import List, Literal
from pydantic import BaseModel, Field

class FlaggedIssue(BaseModel):
    """Represents one failed checkbox or warning note found on the paper checklist."""
    
    # Name of the machine part or check item (e.g., "Oil Seal", "Pressure Gauge")
    item_name: str = Field(description="The checklist item or component name.")
    
    # Restricts the AI to only two valid statuses so downstream code never crashes
    status: Literal["FAIL", "WARNING"] = Field(
        description="Use FAIL if marked broken/unsafe, or WARNING if a minor issue is noted."
    )
    
    # Exact transcription of what the engineer wrote by hand
    handwritten_note: str = Field(
        description="Exact transcription of any handwritten note next to this item."
    )
    
    # AI's initial guess at danger level before our deterministic Python rules run
    severity_hint: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        description="Initial safety risk estimate based on the note."
    )
    
    # Used for Responsible AI: if < 0.75, we force a human to verify the handwriting
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence score (0.0 to 1.0) in reading the handwriting accurately."
    )
    
    # Bounding box in 0-1000 normalized coordinates: [ymin, xmin, ymax, xmax]
    # Pillow uses this later to crop the exact handwriting out of the photo as proof
    box_2d: List[int] = Field(
        min_length=4, max_length=4,
        description="Bounding box [ymin, xmin, ymax, xmax] (0-1000 scale) around the flagged row/note."
    )

class InspectionExtraction(BaseModel):
    """Top-level structure representing the entire scanned safety form."""
    
    # Equipment ID (e.g., "GENERATOR-07") used to look up past history in SQLite
    asset_id: str = Field(
        description="Machine or asset ID written on the form (e.g., GENERATOR-07). Default to UNKNOWN-ASSET if missing."
    )
    
    inspector_name: str = Field(description="Name of the worker who filled out the form.")
    inspection_date: str = Field(description="Date written on the form (YYYY-MM-DD if possible).")
    
    # Compliance check: safety forms without a signature are legally invalid
    signature_present: bool = Field(
        description="True if the inspector signed the bottom of the form, False otherwise."
    )
    
    # List of every problem found on the sheet (empty list if everything passed)
    issues: List[FlaggedIssue] = Field(
        default_factory=list,
        description="All failed items or handwritten warnings found on the checklist."
    )