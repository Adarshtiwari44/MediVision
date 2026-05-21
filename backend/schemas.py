from pydantic import BaseModel

class ChatRequest(BaseModel):
    question: str
    report_text: str
