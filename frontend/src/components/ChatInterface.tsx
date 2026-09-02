import React, { useState } from 'react';
import { Send, Bot, User, Share2, Search, Database } from 'lucide-react';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: { type: 'vector' | 'graph', text: string }[];
}

const ChatInterface = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'Hello! I am your Enterprise GraphRAG assistant. You can ask me questions about your tenant data, and I will use both vector similarity and multi-hop graph traversal to find the answer.',
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSend = () => {
    if (!input.trim()) return;
    
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    setTimeout(() => {
      const isGraphQuery = userMsg.content.toLowerCase().includes('who') || userMsg.content.toLowerCase().includes('connect');
      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Based on the synthesis of your tenant's data, here is the answer to "${userMsg.content}". I've utilized a ${isGraphQuery ? 'HYBRID' : 'VECTOR_SEARCH'} routing strategy to retrieve this context.`,
        sources: [
          { type: 'vector', text: 'Document Chunk #421 from Q3_Financial_Report.pdf' },
          ...(isGraphQuery ? [{ type: 'graph' as const, text: '(Acme Corp)-[OWNS]->(Subsidiary A)-[LOCATED_IN]->(London)' }] : [])
        ]
      };
      setMessages(prev => [...prev, assistantMsg]);
      setIsLoading(false);
    }, 2000);
  };

  return (
    <div className="flex flex-col h-full bg-surface/30">
      <div className="p-6 border-b border-gray-800 bg-surface/50 backdrop-blur-md sticky top-0 z-10 flex justify-between items-center">
        <div>
          <h2 className="text-xl font-bold">Query Agent</h2>
          <p className="text-xs text-gray-400">Agentic Routing: Hybrid (Vector + Graph)</p>
        </div>
        <div className="flex gap-2">
           <span className="px-3 py-1 bg-primary/20 text-primary text-xs font-semibold rounded-full border border-primary/30 flex items-center gap-1 shadow-sm"><Search className="w-3 h-3"/> Vector Ready</span>
           <span className="px-3 py-1 bg-secondary/20 text-secondary text-xs font-semibold rounded-full border border-secondary/30 flex items-center gap-1 shadow-sm"><Share2 className="w-3 h-3"/> Graph Ready</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-4 max-w-4xl mx-auto ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-md ${msg.role === 'user' ? 'bg-primary' : 'bg-surface border border-gray-700'}`}>
              {msg.role === 'user' ? <User className="w-5 h-5 text-white" /> : <Bot className="w-6 h-6 text-emerald-400" />}
            </div>
            <div className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
              <div className={`p-4 rounded-2xl shadow-md ${msg.role === 'user' ? 'bg-primary text-white rounded-tr-none' : 'bg-surface border border-gray-700 text-gray-200 rounded-tl-none'}`}>
                {msg.content}
              </div>
              {msg.sources && (
                <div className="mt-3 flex flex-col gap-2 w-full max-w-lg">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Sources</span>
                  {msg.sources.map((src, idx) => (
                    <div key={idx} className="flex items-start gap-2 bg-gray-900/50 p-2 rounded-lg border border-gray-800 text-xs text-gray-400 shadow-sm">
                      {src.type === 'vector' ? <Database className="w-4 h-4 text-blue-400 shrink-0" /> : <Share2 className="w-4 h-4 text-emerald-400 shrink-0" />}
                      <span>{src.text}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex gap-4 max-w-4xl mx-auto">
             <div className="w-10 h-10 rounded-full bg-surface border border-gray-700 flex items-center justify-center shrink-0 shadow-md">
               <Bot className="w-6 h-6 text-emerald-400 animate-pulse" />
             </div>
             <div className="bg-surface border border-gray-700 p-4 rounded-2xl rounded-tl-none flex gap-1 items-center shadow-md">
               <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
               <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
               <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
               <span className="ml-2 text-sm text-gray-400 font-medium">Synthesizing hybrid response...</span>
             </div>
          </div>
        )}
      </div>

      <div className="p-6 bg-surface/80 border-t border-gray-800 backdrop-blur-md">
        <div className="max-w-4xl mx-auto relative flex items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Ask a multi-hop question (e.g., 'Who is the CEO of the company that acquired XYZ?')"
            className="w-full bg-gray-900 border border-gray-700 rounded-xl py-4 pl-4 pr-14 text-white placeholder-gray-500 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary shadow-inner transition-all"
          />
          <button 
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="absolute right-2 p-2 bg-primary text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:hover:bg-primary transition-colors shadow-md"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;
