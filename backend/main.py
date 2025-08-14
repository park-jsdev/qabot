from fastapi import FastAPI, Request, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
from pathlib import Path
import shutil
import asyncio
import logging
from datetime import datetime
from langchain_community.document_loaders import UnstructuredWordDocumentLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS
from langchain.embeddings import OllamaEmbeddings
from langchain.llms import Ollama
from langchain.chains import RetrievalQAWithSourcesChain
import re
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rag.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class Message(BaseModel):
    role: str
    content: str

class QueryRequest(BaseModel):
    question: str
    chat_history: Optional[List[Message]] = []

class Document(BaseModel):
    id: str
    title: str
    path: str
    type: str
    folder: str

class FolderStructure(BaseModel):
    name: str
    path: str
    type: str
    children: Optional[List['FolderStructure']] = None

class FolderUploadRequest(BaseModel):
    folder_path: str

# Configuration
DOCS_DIR = Path("documents")
UPLOAD_DIR = Path("uploads")
FAISS_INDEX_DIR = Path("faiss_index")

# Create necessary directories
DOCS_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
FAISS_INDEX_DIR.mkdir(exist_ok=True)

# Initialize RAG components
embeddings = OllamaEmbeddings(model="mistral")
vectorstore = None
llm = Ollama(model="mistral")

def initialize_vectorstore():
    global vectorstore
    if FAISS_INDEX_DIR.exists() and any(FAISS_INDEX_DIR.iterdir()):
        vectorstore = FAISS.load_local(str(FAISS_INDEX_DIR), embeddings, allow_dangerous_deserialization=True)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
        return RetrievalQAWithSourcesChain.from_chain_type(
            llm=llm,
            retriever=retriever,
            return_source_documents=True,
            chain_type="stuff"
        )
    return None

qa_chain = initialize_vectorstore()

def build_folder_structure(path: Path, base_path: Path) -> FolderStructure:
    """Build a tree structure representing the folder hierarchy"""
    if path.is_file():
        return FolderStructure(
            name=path.name,
            path=str(path.relative_to(base_path)),
            type="file"
        )
    
    children = []
    # Sort items to show folders first, then files
    items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    
    for item in items:
        if item.is_file() and item.suffix.lower() in ['.doc', '.docx']:
            children.append(FolderStructure(
                name=item.name,
                path=str(item.relative_to(base_path)),
                type="file"
            ))
        elif item.is_dir():
            children.append(build_folder_structure(item, base_path))
    
    return FolderStructure(
        name=path.name,
        path=str(path.relative_to(base_path)),
        type="folder",
        children=children
    )

def process_documents():
    """Process all documents in the documents directory and its subdirectories"""
    documents = []
    logger.info("Starting document processing...")
    
    # Walk through all subdirectories
    for root, _, files in os.walk(DOCS_DIR):
        for file in files:
            if file.endswith(('.doc', '.docx')):
                file_path = Path(root) / file
                try:
                    logger.info(f"Processing file: {file_path}")
                    loader = UnstructuredWordDocumentLoader(
                        str(file_path),
                        mode="elements"
                    )
                    docs = loader.load()
                    # Add source metadata and filename to content for each doc
                    for doc in docs:
                        doc.metadata['source'] = str(file_path)
                        doc.page_content = f"[SOURCE: {file_path.name}]\n" + doc.page_content
                    documents.extend(docs)
                    logger.info(f"Successfully loaded {len(docs)} elements from {file_path}")
                except Exception as e:
                    logger.error(f"Error loading {file_path}: {e}")

    if not documents:
        logger.warning("No documents found to process")
        return False

    logger.info(f"Total documents loaded: {len(documents)}")

    # Chunk documents
    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)
    chunks = splitter.split_documents(documents)
    logger.info(f"Split into {len(chunks)} chunks")
    
    if not chunks:
        logger.error("No chunks created from documents")
        return False

    # Create embeddings and save to FAISS
    logger.info("Creating embeddings and saving to FAISS...")
    global vectorstore

    try:
        logger.info(f"Indexing with FAISS from documents...")
        vectorstore = FAISS.from_documents(chunks, embeddings)
        logger.info("Saving FAISS index to disk...")
        vectorstore.save_local(str(FAISS_INDEX_DIR))
        logger.info("Vector store created and saved successfully")
    except Exception as e:
        logger.error(f"Error saving to FAISS: {e}")
        return False
    
    return True

def extract_possible_entities(query):
    date_pattern = r"\b(?:\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2})\b"
    name_pattern = r"[A-Z][a-z]+ [A-Z][a-z]+"
    serial_pattern = r"[A-Z0-9#-]{6,}"
    dates = re.findall(date_pattern, query)
    names = re.findall(name_pattern, query)
    records = re.findall(serial_pattern, query)
    return set(dates + names + records)

def metadata_search(entity_values, vectorstore):
    all_docs = vectorstore.docstore._dict.values()
    hits = []
    for doc in all_docs:
        found = False
        for field in ["dates", "names", "records", "underlined"]:
            meta_values = doc.metadata.get(field, [])
            if isinstance(meta_values, str):
                meta_values = [meta_values]
            for entity in entity_values:
                if entity in meta_values:
                    found = True
        for field in ["heading", "version", "revision", "source"]:
            meta_value = doc.metadata.get(field)
            if meta_value and any(entity in str(meta_value) for entity in entity_values):
                found = True
        if found:
            hits.append(doc)
    return hits

# --- Async wrapper for sync generators ---
async def async_wrap_generator(sync_gen):
    for item in sync_gen:
        yield item
        await asyncio.sleep(0)

# --- Update streaming response to use async wrapper ---
async def generate_streaming_response(query: str):
    """Generate streaming response for the chat endpoint"""
    try:
        if not vectorstore:
            yield json.dumps({"error": "Vector store not initialized. Please run indexing first."}) + "\n"
            return

        # Hybrid search approach
        entity_values = extract_possible_entities(query)
        entity_hits = metadata_search(entity_values, vectorstore) if entity_values else []
        
        if entity_hits:
            docs = entity_hits[:5]
            answer_context = " ".join([doc.page_content for doc in docs])
            sources = "; ".join(set([doc.metadata.get("source", "N/A") for doc in docs]))
            
            # Stream the response from the LLM (wrap sync generator)
            response = llm.stream(answer_context + "\n\n" + query)
            async for chunk in async_wrap_generator(response):
                yield json.dumps({"chunk": chunk}) + "\n"
            # Send sources after the response
            yield json.dumps({"sources": sources}) + "\n"
        else:
            # Fallback to semantic search
            result = qa_chain(query)
            # Return answer and sources (with metadata)
            yield json.dumps({"chunk": result['answer']}) + "\n"
            yield json.dumps({"sources": result['sources']}) + "\n"
            # Optionally, you can add more metadata here if available
        
    except Exception as e:
        yield json.dumps({"error": str(e)}) + "\n"

@app.post("/api/chat")
async def chat_endpoint(req: QueryRequest):
    return StreamingResponse(
        generate_streaming_response(req.question),
        media_type="application/x-ndjson"
    )

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        file_path = UPLOAD_DIR / file.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Move the file to the documents directory
        target_path = DOCS_DIR / file.filename
        shutil.move(str(file_path), str(target_path))
        
        return {"message": "File uploaded successfully", "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload-folder")
async def upload_folder(request: FolderUploadRequest):
    """Upload an entire folder structure"""
    try:
        source_path = Path(request.folder_path)
        if not source_path.exists():
            raise HTTPException(status_code=400, detail="Source folder does not exist")

        # Create the target folder in DOCS_DIR
        target_path = DOCS_DIR / source_path.name
        if target_path.exists():
            # If folder already exists, add a timestamp to make it unique
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_path = DOCS_DIR / f"{source_path.name}_{timestamp}"
        target_path.mkdir(exist_ok=True)

        # Copy the entire folder structure
        for item in source_path.rglob("*"):
            if item.is_file() and item.suffix.lower() in ['.doc', '.docx']:
                relative_path = item.relative_to(source_path)
                target_item = target_path / relative_path
                target_item.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target_item)
                logger.info(f"Copied {item} to {target_item}")

        return {"message": "Folder uploaded successfully", "path": str(target_path)}
    except Exception as e:
        logger.error(f"Error uploading folder: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload-folder-files")
async def upload_folder_files(files: List[UploadFile] = File(...), relative_paths: List[str] = Form(...)):
    """Upload multiple files with their relative paths and save them to the documents directory."""
    try:
        for file, rel_path in zip(files, relative_paths):
            target_path = DOCS_DIR / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            logger.info(f"Saved {file.filename} to {target_path}")
        return {"message": "Files uploaded and saved successfully"}
    except Exception as e:
        logger.error(f"Error uploading folder files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/folder-structure")
async def get_folder_structure():
    """Get the current folder structure"""
    try:
        structure = build_folder_structure(DOCS_DIR, DOCS_DIR)
        logger.info(f"Built folder structure: {structure}")
        return structure
    except Exception as e:
        logger.error(f"Error getting folder structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/index")
async def index_documents():
    """Endpoint to trigger document indexing"""
    try:
        logger.info("Starting document indexing process")
        success = process_documents()
        if success:
            # Reinitialize the QA chain with the new vectorstore
            global qa_chain
            qa_chain = initialize_vectorstore()
            logger.info("Document indexing completed successfully")
            return {"message": "Documents indexed successfully"}
        else:
            logger.warning("No documents found to index")
            raise HTTPException(status_code=400, detail="No documents found to index")
    except Exception as e:
        logger.error(f"Error during indexing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents")
async def list_documents():
    try:
        documents = []
        for file_path in DOCS_DIR.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in ['.doc', '.docx']:
                documents.append({
                    "id": str(file_path.stem),
                    "title": file_path.name,
                    "path": str(file_path.relative_to(DOCS_DIR)),
                    "type": file_path.suffix[1:]
                })
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/documents/{document_path:path}")
async def delete_document(document_path: str):
    """Delete a document or folder by its path"""
    try:
        # Ensure the path is relative to DOCS_DIR
        target_path = DOCS_DIR / document_path
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="Document or folder not found")
        
        # Ensure the path is within DOCS_DIR
        if not str(target_path).startswith(str(DOCS_DIR)):
            raise HTTPException(status_code=400, detail="Invalid path")
        
        if target_path.is_file():
            target_path.unlink()
            logger.info(f"Deleted file: {target_path}")
        elif target_path.is_dir():
            # Delete all files in the directory
            for item in target_path.rglob("*"):
                if item.is_file():
                    item.unlink()
                    logger.info(f"Deleted file: {item}")
            
            # Delete all subdirectories
            for item in sorted(target_path.rglob("*"), reverse=True):
                if item.is_dir():
                    item.rmdir()
                    logger.info(f"Deleted directory: {item}")
            
            # Delete the target directory itself
            target_path.rmdir()
            logger.info(f"Deleted directory: {target_path}")
        
        return {"message": "Item deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting item: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/documents")
async def delete_all_documents():
    """Delete all documents and clear the FAISS index"""
    try:
        # Delete all files in DOCS_DIR
        for item in DOCS_DIR.rglob("*"):
            if item.is_file():
                item.unlink()
                logger.info(f"Deleted file: {item}")
        
        # Delete all directories in DOCS_DIR (except DOCS_DIR itself)
        for item in sorted(DOCS_DIR.rglob("*"), reverse=True):
            if item.is_dir() and item != DOCS_DIR:
                item.rmdir()
                logger.info(f"Deleted directory: {item}")
        
        # Clear FAISS index
        if FAISS_INDEX_DIR.exists():
            for item in FAISS_INDEX_DIR.iterdir():
                if item.is_file():
                    item.unlink()
            logger.info("Cleared FAISS index")
        
        # Reinitialize vectorstore
        global vectorstore, qa_chain
        vectorstore = None
        qa_chain = None
        
        return {"message": "All documents and index cleared successfully"}
    except Exception as e:
        logger.error(f"Error deleting all documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
