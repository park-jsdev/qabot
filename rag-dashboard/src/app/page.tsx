'use client';

import { useState, useRef, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import Image from "next/image";
import DocumentPanel from '@/components/DocumentPanel';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: string;
}

interface Document {
  id: string;
  title: string;
  path: string;
  type: string;
  folder: string;
}

interface FolderStructure {
  name: string;
  path: string;
  type: string;
  children?: FolderStructure[];
  isExpanded?: boolean;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [folderStructure, setFolderStructure] = useState<FolderStructure | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isIndexing, setIsIndexing] = useState(false);
  const [indexingLog, setIndexingLog] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { getRootProps, getInputProps } = useDropzone({
    onDrop: async (acceptedFiles) => {
      for (const file of acceptedFiles) {
        const formData = new FormData();
        formData.append('file', file);
        
        try {
          const response = await fetch('http://localhost:8000/api/upload', {
            method: 'POST',
            body: formData,
          });
          
          if (response.ok) {
            fetchFolderStructure();
          }
        } catch (error) {
          console.error('Error uploading file:', error);
        }
      }
    },
  });

  const fetchFolderStructure = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/folder-structure');
      const data = await response.json();
      setFolderStructure(data);
    } catch (error) {
      console.error('Error fetching folder structure:', error);
    }
  };

  const handleFolderSelect = async () => {
    try {
      // Create a hidden input element
      const input = document.createElement('input');
      input.type = 'file';
      // @ts-ignore - webkitdirectory is a valid property but TypeScript doesn't know about it
      input.webkitdirectory = true;
      input.multiple = true;
      
      input.onchange = async (e) => {
        const files = (e.target as HTMLInputElement).files;
        if (files && files.length > 0) {
          const formData = new FormData();
          for (let i = 0; i < files.length; i++) {
            const file = files[i];
            // @ts-ignore - webkitRelativePath is supported in browsers
            const relPath = (file as any).webkitRelativePath || file.name;
            formData.append('files', file);
            formData.append('relative_paths', relPath);
          }
          const response = await fetch('http://localhost:8000/api/upload-folder-files', {
            method: 'POST',
            body: formData,
          });
          if (response.ok) {
            fetchFolderStructure();
          } else {
            const errorData = await response.json();
            console.error('Error uploading folder:', errorData);
            alert('Error uploading folder: ' + (errorData.detail || 'Unknown error'));
          }
        }
      };
      
      input.click();
    } catch (error) {
      console.error('Error selecting folder:', error);
    }
  };

  const handleIndexDocuments = async () => {
    setIsIndexing(true);
    setIndexingLog([]);
    try {
      const response = await fetch('http://localhost:8000/api/index', {
        method: 'POST',
      });
      const data = await response.json();
      if (response.ok) {
        setIndexingLog(prev => [...prev, 'Documents indexed successfully!']);
      } else {
        setIndexingLog(prev => [...prev, `Error: ${data.detail}`]);
      }
    } catch (error) {
      console.error('Error indexing documents:', error);
      setIndexingLog(prev => [...prev, 'Error indexing documents. Please try again.']);
    } finally {
      setIsIndexing(false);
    }
  };

  useEffect(() => {
    fetchFolderStructure();
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: input,
          chat_history: messages,
        }),
      });

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader!.read();
        if (done) break;
        
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n').filter(Boolean);
        
        for (const line of lines) {
          const data = JSON.parse(line);
          if (data.error) {
            console.error(data.error);
            setMessages(prev => [...prev, { role: 'assistant', content: 'Error: ' + data.error }]);
          } else if (data.chunk) {
            setMessages(prev => {
              const lastMessage = prev[prev.length - 1];
              if (lastMessage.role === 'assistant') {
                return [
                  ...prev.slice(0, -1),
                  { ...lastMessage, content: lastMessage.content + data.chunk }
                ];
              }
              return [...prev, { role: 'assistant', content: data.chunk }];
            });
          } else if (data.sources) {
            setMessages(prev => {
              const lastMessage = prev[prev.length - 1];
              if (lastMessage.role === 'assistant') {
                return [
                  ...prev.slice(0, -1),
                  { ...lastMessage, sources: data.sources }
                ];
              }
              return prev;
            });
          }
        }
      }
    } catch (error) {
      console.error('Error sending message:', error);
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error: Failed to get response' }]);
    } finally {
      setIsLoading(false);
    }
  };

  const deleteDocument = async (path: string) => {
    try {
      const response = await fetch(`http://localhost:8000/api/documents/${encodeURIComponent(path)}`, {
        method: 'DELETE',
      });
      
      if (response.ok) {
        fetchFolderStructure();
      } else {
        const errorData = await response.json();
        console.error('Error deleting document:', errorData);
        alert(`Failed to delete document: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error deleting document:', error);
      alert('Failed to delete document. Please try again.');
    }
  };

  const deleteAllDocuments = async () => {
    if (!confirm('Are you sure you want to delete all documents? This action cannot be undone.')) {
      return;
    }

    try {
      const response = await fetch('http://localhost:8000/api/documents', {
        method: 'DELETE',
      });
      
      if (response.ok) {
        fetchFolderStructure();
        setMessages([]); // Clear chat history
      } else {
        const errorData = await response.json();
        console.error('Error deleting all documents:', errorData);
        alert(`Failed to delete all documents: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error deleting all documents:', error);
      alert('Failed to delete all documents. Please try again.');
    }
  };

  const cleanFolderName = (name: string) => {
    // Remove timestamp pattern from folder names
    return name.replace(/_\d{8}_\d{6}$/, '');
  };

  const toggleFolder = (path: string) => {
    setFolderStructure(prev => {
      if (!prev) return null;
      
      const updateFolder = (folder: FolderStructure): FolderStructure => {
        if (folder.path === path) {
          return { ...folder, isExpanded: !folder.isExpanded };
        }
        if (folder.children) {
          return {
            ...folder,
            children: folder.children.map(updateFolder)
          };
        }
        return folder;
      };
      
      return updateFolder(prev);
    });
  };

  const deleteFolder = async (path: string) => {
    if (!confirm('Are you sure you want to delete this folder and all its contents?')) {
      return;
    }

    try {
      const response = await fetch(`http://localhost:8000/api/documents/${encodeURIComponent(path)}`, {
        method: 'DELETE',
      });
      
      if (response.ok) {
        fetchFolderStructure();
      } else {
        const errorData = await response.json();
        console.error('Error deleting folder:', errorData);
        alert(`Failed to delete folder: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error deleting folder:', error);
      alert('Failed to delete folder. Please try again.');
    }
  };

  const renderFolderStructure = (item: FolderStructure, level: number = 0) => {
    const paddingLeft = `${level * 1.5}rem`;
    
    if (item.type === 'file') {
      return (
        <div key={item.path} style={{ paddingLeft }} className="flex justify-between items-center p-2 hover:bg-gray-200 dark:hover:bg-gray-600">
          <div className="flex items-center space-x-2">
            <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span className="truncate">{item.name}</span>
          </div>
          <button
            onClick={() => deleteDocument(item.path)}
            className="text-red-500 hover:text-red-700"
          >
            Delete
          </button>
        </div>
      );
    }

    // Don't render the root "documents" folder
    if (item.name === "documents" && level === 0) {
      return (
        <div key={item.path}>
          {item.children?.map(child => renderFolderStructure(child, level))}
        </div>
      );
    }

    const isExpanded = item.isExpanded ?? true;

    return (
      <div key={item.path}>
        <div 
          style={{ paddingLeft }} 
          className="flex justify-between items-center p-2 hover:bg-gray-200 dark:hover:bg-gray-600 cursor-pointer"
          onClick={() => toggleFolder(item.path)}
        >
          <div className="flex items-center space-x-2">
            <svg 
              className={`w-4 h-4 text-gray-500 transform transition-transform ${isExpanded ? 'rotate-90' : ''}`} 
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
            <span className="font-semibold">{cleanFolderName(item.name)}</span>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              deleteFolder(item.path);
            }}
            className="text-red-500 hover:text-red-700"
          >
            Delete
          </button>
        </div>
        {isExpanded && item.children && item.children.length > 0 && (
          <div>
            {item.children.map(child => renderFolderStructure(child, level + 1))}
          </div>
        )}
      </div>
    );
  };

  // Add a debug log to check the folder structure
  useEffect(() => {
    if (folderStructure) {
      console.log('Current folder structure:', folderStructure);
    }
  }, [folderStructure]);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="flex h-screen">
        {/* Document Panel */}
        <div className="w-1/4 bg-white dark:bg-gray-800 p-4 overflow-y-auto">
          <div className="mb-4">
            <h2 className="text-xl font-bold mb-2">Documents</h2>
            <div className="space-y-2">
              <button
                onClick={handleFolderSelect}
                className="w-full bg-green-500 text-white p-2 rounded hover:bg-green-600"
              >
                Select Folder
              </button>
              <button
                onClick={handleIndexDocuments}
                disabled={isIndexing}
                className="w-full bg-blue-500 text-white p-2 rounded hover:bg-blue-600 disabled:bg-gray-400"
              >
                {isIndexing ? 'Indexing...' : 'Index Documents'}
              </button>
              <button
                onClick={deleteAllDocuments}
                className="w-full bg-red-500 text-white p-2 rounded hover:bg-red-600"
              >
                Delete All Documents
              </button>
              <div {...getRootProps()} className="border-2 border-dashed border-gray-300 p-4 rounded text-center cursor-pointer">
                <input {...getInputProps()} />
                <p>Or drag & drop files here</p>
              </div>
            </div>
          </div>

          {/* Indexing Log */}
          {indexingLog.length > 0 && (
            <div className="mb-4 p-2 bg-gray-100 dark:bg-gray-700 rounded">
              <h3 className="font-semibold mb-2">Indexing Log:</h3>
              <div className="space-y-1 text-sm">
                {indexingLog.map((log, index) => (
                  <div key={index} className="text-gray-600 dark:text-gray-300">
                    {log}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Folder Structure */}
          <div className="space-y-2">
            {folderStructure && renderFolderStructure(folderStructure)}
          </div>
        </div>

        {/* Chat Interface */}
        <div className="flex-1 flex flex-col">
          <div className="flex-1 overflow-y-auto p-4">
            <div className="max-w-3xl mx-auto space-y-4">
              {messages.map((message, index) => (
                <div
                  key={index}
                  className={`flex ${
                    message.role === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  <div
                    className={`max-w-[80%] rounded-lg p-3 ${
                      message.role === 'user'
                        ? 'bg-blue-500 text-white'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100'
                    }`}
                  >
                    <div>{message.content}</div>
                    {message.sources && (
                      <div className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                        Sources: {message.sources}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input Form */}
          <form onSubmit={handleSubmit} className="p-4 border-t dark:border-gray-700">
            <div className="max-w-3xl mx-auto flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a question..."
                className="flex-1 p-2 border rounded dark:bg-gray-800 dark:border-gray-700"
                disabled={isLoading}
              />
              <button
                type="submit"
                disabled={isLoading}
                className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600 disabled:bg-gray-400"
              >
                {isLoading ? 'Sending...' : 'Send'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
