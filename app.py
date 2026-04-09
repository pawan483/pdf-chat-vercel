import os
import re
import tempfile
from typing import List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
from pypdf import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter

app = FastAPI(title="PDF Chat Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
retriever_global: List[Dict[str, Any]] = []


class AskRequest(BaseModel):
    message: str


def normalize_words(text: str):
    return set(re.findall(r"\w+", text.lower()))


def process_pdf_file(file_path: str):
    global retriever_global

    reader = PdfReader(file_path)
    pages = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({"text": text, "page": i + 1})

    if not pages:
        return {"status": "error", "message": "Could not extract text from this PDF."}

    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=40)

    chunks = []
    for p in pages:
        split_chunks = splitter.split_text(p["text"])
        for chunk in split_chunks:
            chunks.append({"text": chunk, "page": p["page"]})

    if not chunks:
        return {"status": "error", "message": "No content could be chunked from this PDF."}

    retriever_global = chunks
    return {
        "status": "success",
        "message": f"PDF processed successfully. {len(chunks)} chunks indexed.",
        "chunks": len(chunks),
    }


def retrieve_relevant_chunks(query: str, top_k: int = 4):
    global retriever_global

    query_words = normalize_words(query)
    scored = []

    for chunk in retriever_global:
        chunk_words = normalize_words(chunk["text"])
        score = len(query_words.intersection(chunk_words))
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:top_k] if item[0] > 0]


def generate_answer(message: str):
    global retriever_global

    if not retriever_global:
        return {
            "status": "error",
            "answer": "Please upload a PDF first.",
            "sources": [],
        }

    results = retrieve_relevant_chunks(message, top_k=4)

    if not results:
        return {
            "status": "success",
            "answer": "I don't know.",
            "sources": [],
        }

    docs = [r["text"] for r in results]
    sources = sorted(list(set(str(r["page"]) for r in results)))
    context = "\n\n".join([d[:400] for d in docs])

    prompt = f"""You are an expert AI assistant.

Rules:
- Give a short definition
- Then summarize in bullet points
- Keep it simple and clear
- If the answer is not in the context, say "I don't know"

Context:
{context}

Question:
{message}

Answer:"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant."},
                {"role": "user", "content": prompt},
            ],
        )
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        return {
            "status": "error",
            "answer": f"LLM Error: {str(e)}",
            "sources": [],
        }

    if "Answer:" in answer:
        answer = answer.split("Answer:")[-1].strip()

    return {
        "status": "success",
        "answer": answer,
        "sources": sources,
    }


@app.get("/")
def root():
    return {
        "message": "PDF Chat Assistant API is running on Vercel"
    }


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(await file.read())
        temp_path = temp_file.name

    try:
        result = process_pdf_file(temp_path)
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        return result
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/ask")
async def ask_question(request: AskRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    result = generate_answer(request.message)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["answer"])

    return result


@app.post("/upload-and-ask")
async def upload_and_ask(
    message: str = Form(...),
    file: UploadFile = File(...)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(await file.read())
        temp_path = temp_file.name

    try:
        pdf_result = process_pdf_file(temp_path)
        if pdf_result["status"] == "error":
            raise HTTPException(status_code=400, detail=pdf_result["message"])

        ask_result = generate_answer(message)
        if ask_result["status"] == "error":
            raise HTTPException(status_code=400, detail=ask_result["answer"])

        return {
            "pdf": pdf_result,
            "response": ask_result,
        }
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
