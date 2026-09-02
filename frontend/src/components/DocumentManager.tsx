import React, { useState } from 'react';
import { UploadCloud, FileText, CheckCircle2, Loader2 } from 'lucide-react';

const DocumentManager = () => {
  const [isUploading, setIsUploading] = useState(false);
  const [docs, setDocs] = useState([
    { id: '1', name: 'Q3_Financial_Report.pdf', status: 'completed', date: '2023-10-15' },
    { id: '2', name: 'Engineering_Architecture_v2.md', status: 'completed', date: '2023-10-14' },
  ]);

  const handleUpload = () => {
    setIsUploading(true);
    setTimeout(() => {
      setDocs([{ id: Date.now().toString(), name: 'New_Dataset.csv', status: 'processing', date: new Date().toISOString().split('T')[0] }, ...docs]);
      setIsUploading(false);
      
      // Simulate processing completion
      setTimeout(() => {
        setDocs(prev => prev.map(d => d.status === 'processing' ? { ...d, status: 'completed' } : d));
      }, 3000);
    }, 1000);
  };

  return (
    <div className="p-8 h-full flex flex-col overflow-y-auto">
      <div className="mb-8">
        <h2 className="text-3xl font-bold mb-2">Document Knowledge Base</h2>
        <p className="text-gray-400">Upload documents to expand your tenant's knowledge graph and vector space.</p>
      </div>

      <div 
        className="border-2 border-dashed border-gray-700 rounded-2xl p-12 flex flex-col items-center justify-center bg-surface/50 backdrop-blur-sm transition-all hover:border-primary/50 group cursor-pointer mb-8 shadow-lg"
        onClick={handleUpload}
      >
        <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
          {isUploading ? (
            <Loader2 className="w-10 h-10 text-primary animate-spin" />
          ) : (
            <UploadCloud className="w-10 h-10 text-primary" />
          )}
        </div>
        <h3 className="text-xl font-semibold mb-2">Click to Upload Documents</h3>
        <p className="text-gray-500 max-w-md text-center text-sm">
          Supports PDF, Markdown, TXT, and CSV. Documents are automatically chunked, embedded into Qdrant, and processed into Neo4j graph nodes via Celery workers.
        </p>
      </div>

      <div className="flex-1">
        <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <FileText className="w-5 h-5 text-gray-400" />
          Processed Documents
        </h3>
        <div className="grid gap-4">
          {docs.map(doc => (
            <div key={doc.id} className="bg-surface/80 border border-gray-800 rounded-xl p-4 flex items-center justify-between hover:border-gray-600 transition-colors shadow-md">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gray-800 rounded-lg text-gray-300">
                  <FileText className="w-6 h-6" />
                </div>
                <div>
                  <h4 className="font-medium text-gray-200">{doc.name}</h4>
                  <p className="text-xs text-gray-500">Uploaded {doc.date}</p>
                </div>
              </div>
              <div>
                {doc.status === 'completed' ? (
                  <span className="flex items-center gap-2 text-sm font-medium text-secondary bg-secondary/10 px-3 py-1 rounded-full border border-secondary/20 shadow-sm">
                    <CheckCircle2 className="w-4 h-4" /> Ready
                  </span>
                ) : (
                  <span className="flex items-center gap-2 text-sm font-medium text-blue-400 bg-blue-400/10 px-3 py-1 rounded-full border border-blue-400/20 shadow-sm">
                    <Loader2 className="w-4 h-4 animate-spin" /> Processing Graph...
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default DocumentManager;
