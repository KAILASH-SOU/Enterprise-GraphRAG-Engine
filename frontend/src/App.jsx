import React, { useState } from 'react';
import DocumentManager from './components/DocumentManager';
import ChatInterface from './components/ChatInterface';
import GraphCanvas from './components/GraphCanvas';
import { Database, MessageSquare, Network } from 'lucide-react';

function App() {
  const [activeTab, setActiveTab] = useState('chat');

  return (
    <div className="flex h-screen bg-background font-sans text-gray-100 overflow-hidden">
      {/* Sidebar */}
      <div className="w-64 bg-surface border-r border-gray-800 flex flex-col shadow-2xl z-10 relative">
        <div className="p-6 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <Network className="w-8 h-8 text-primary" />
            <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-primary to-secondary">
              GraphRAG
            </h1>
          </div>
          <p className="text-xs text-gray-400 mt-2">Enterprise Knowledge Engine</p>
        </div>
        
        <nav className="flex-1 px-4 py-6 space-y-2">
          <button 
            onClick={() => setActiveTab('chat')}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300 ${activeTab === 'chat' ? 'bg-primary/10 text-primary shadow-inner border border-primary/20' : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'}`}
          >
            <MessageSquare className="w-5 h-5" />
            <span className="font-medium">Query & Chat</span>
          </button>
          
          <button 
            onClick={() => setActiveTab('documents')}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300 ${activeTab === 'documents' ? 'bg-primary/10 text-primary shadow-inner border border-primary/20' : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'}`}
          >
            <Database className="w-5 h-5" />
            <span className="font-medium">Documents</span>
          </button>
          
          <button 
            onClick={() => setActiveTab('graph')}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300 ${activeTab === 'graph' ? 'bg-primary/10 text-primary shadow-inner border border-primary/20' : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'}`}
          >
            <Network className="w-5 h-5" />
            <span className="font-medium">Knowledge Graph</span>
          </button>
        </nav>
        
        <div className="p-4 border-t border-gray-800">
          <div className="flex items-center gap-3 px-4 py-2">
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-primary to-secondary flex items-center justify-center text-sm font-bold shadow-lg">
              T1
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-medium text-gray-200">Tenant Acme</span>
              <span className="text-xs text-gray-500">ID: tenant_123</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 relative bg-gradient-to-br from-background to-[#111827]">
        {/* Subtle background grid pattern */}
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wNSkiLz48L3N2Zz4=')] opacity-50"></div>
        
        <div className="relative h-full z-0 flex flex-col">
          {activeTab === 'chat' && <ChatInterface />}
          {activeTab === 'documents' && <DocumentManager />}
          {activeTab === 'graph' && <GraphCanvas />}
        </div>
      </div>
    </div>
  );
}

export default App;
