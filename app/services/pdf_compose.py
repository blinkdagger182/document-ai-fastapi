from typing import List, Dict
from uuid import UUID
import fitz  # PyMuPDF
from app.models.field import FieldRegion, FieldValue, FieldType


class PDFComposer:
    def compose_pdf(
        self,
        original_pdf_path: str,
        output_pdf_path: str,
        field_regions: List[FieldRegion],
        field_values: Dict[UUID, str]
    ) -> None:
        """
        Compose a filled PDF by overlaying field values onto the original PDF.
        
        Args:
            original_pdf_path: Path to original PDF
            output_pdf_path: Path to save filled PDF
            field_regions: List of field region definitions
            field_values: Dict mapping field_region_id to value
        """
        doc = fitz.open(original_pdf_path)
        
        for field_region in field_regions:
            if field_region.id not in field_values:
                continue
            
            value = field_values[field_region.id]
            if not value:
                continue
            
            page = doc[field_region.page_index]
            page_rect = page.rect
            
            # Convert normalized coordinates to PDF points
            x = field_region.x * page_rect.width
            y = field_region.y * page_rect.height
            width = field_region.width * page_rect.width
            height = field_region.height * page_rect.height
            
            rect = fitz.Rect(x, y, x + width, y + height)
            
            if field_region.field_type == FieldType.checkbox:
                # Draw checkbox
                if value.lower() in ['true', 'yes', '1', 'checked']:
                    # Draw X or checkmark
                    page.draw_line(rect.top_left, rect.bottom_right, color=(0, 0, 0), width=2)
                    page.draw_line(rect.top_right, rect.bottom_left, color=(0, 0, 0), width=2)
            else:
                # Draw text
                fontsize = min(height * 0.7, 12)  # Adaptive font size
                
                # Add white background
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                
                # Insert text
                try:
                    page.insert_textbox(
                        rect,
                        value,
                        fontsize=fontsize,
                        color=(0, 0, 0),
                        align=fitz.TEXT_ALIGN_LEFT
                    )
                except Exception as e:
                    # Fallback: just draw text at position
                    page.insert_text(
                        (x + 2, y + height - 2),
                        value,
                        fontsize=fontsize,
                        color=(0, 0, 0)
                    )
        
        doc.save(output_pdf_path)
        doc.close()
