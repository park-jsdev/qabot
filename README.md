# QA Bot: RAG Document QA System

A minimal Retrieval-Augmented Generation (RAG) system for document-based question answering, featuring:
- **FastAPI backend** for document indexing, retrieval, and chat.
- **Next.js dashboard** for uploading documents and interacting with the QA system.

---

## Features

- Upload and index `.doc`/`.docx` documents.
- Ask questions and get answers with sources.
- Modern, minimal dashboard UI.

---

## Prerequisites

- Python 3.9+
- Node.js 18+

---

## Backend Setup (FastAPI)

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the backend server:**
   ```bash
   uvicorn backend.main:app --reload
   ```
   The API will be available at [http://localhost:8000](http://localhost:8000).

3. **Check server health:**
   ```bash
   curl http://localhost:8000/api/health
   ```
   Should return a JSON status payload.

---

## Frontend Setup (Next.js Dashboard)

1. **Install dependencies:**
   ```bash
   cd rag-dashboard
   npm install
   ```

2. **Run the development server:**
   ```bash
   npm run dev
   ```
   The dashboard will be available at [http://localhost:3000](http://localhost:3000).

---

## Usage

- Open the dashboard in your browser.
- Upload your documents.
- Ask questions and receive answers with document references.

---

## Project Structure

```
backend/         # FastAPI backend
rag-dashboard/   # Next.js frontend
index_documents.py, query_documents.py  # Utilities for document indexing/querying
requirements.txt # Python dependencies
```
