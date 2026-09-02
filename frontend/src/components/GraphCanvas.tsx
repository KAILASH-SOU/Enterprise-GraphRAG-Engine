import React, { useRef, useEffect, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { Network, Maximize2, Filter } from 'lucide-react';

const mockData = {
  nodes: [
    { id: 'Alice', group: 'PERSON', val: 2 },
    { id: 'Bob', group: 'PERSON', val: 2 },
    { id: 'Acme Corp', group: 'ORGANIZATION', val: 4 },
    { id: 'Project X', group: 'PROJECT', val: 3 },
    { id: 'London', group: 'LOCATION', val: 2 },
  ],
  links: [
    { source: 'Alice', target: 'Acme Corp', label: 'WORKS_FOR' },
    { source: 'Bob', target: 'Acme Corp', label: 'WORKS_FOR' },
    { source: 'Alice', target: 'Project X', label: 'LEADS' },
    { source: 'Bob', target: 'Project X', label: 'CONTRIBUTES_TO' },
    { source: 'Acme Corp', target: 'London', label: 'HQ_LOCATED_IN' },
  ]
};

const getColor = (group: string) => {
  switch (group) {
    case 'PERSON': return '#3B82F6';
    case 'ORGANIZATION': return '#10B981';
    case 'PROJECT': return '#F59E0B';
    case 'LOCATION': return '#8B5CF6';
    default: return '#9CA3AF';
  }
};

const GraphCanvas = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [selectedNode, setSelectedNode] = useState<any>(null);

  useEffect(() => {
    if (containerRef.current) {
      setDimensions({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight
      });
    }

    const handleResize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight
        });
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return (
    <div className="flex h-full w-full relative">
      <div ref={containerRef} className="flex-1 bg-[#0B0F19]">
        <ForceGraph2D
          width={dimensions.width}
          height={dimensions.height}
          graphData={mockData}
          nodeLabel="id"
          nodeColor={node => getColor(node.group as string)}
          nodeRelSize={6}
          linkColor={() => 'rgba(255,255,255,0.2)'}
          linkDirectionalArrowLength={3.5}
          linkDirectionalArrowRelPos={1}
          onNodeClick={(node) => setSelectedNode(node)}
          linkCanvasObjectMode={() => 'after'}
          linkCanvasObject={(link: any, ctx, globalScale) => {
            const MAX_FONT_SIZE = 4;
            const label = link.label;
            const fontSize = MAX_FONT_SIZE;
            ctx.font = `${fontSize}px Sans-Serif`;
            const textWidth = ctx.measureText(label).width;
            const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2);

            ctx.save();
            if (link.source.x !== undefined && link.target.x !== undefined) {
              const x = link.source.x + (link.target.x - link.source.x) / 2;
              const y = link.source.y + (link.target.y - link.source.y) / 2;
              
              ctx.translate(x, y);
              
              const angle = Math.atan2(link.target.y - link.source.y, link.target.x - link.source.x);
              let drawAngle = angle;
              if (drawAngle > Math.PI / 2 || drawAngle < -Math.PI / 2) {
                drawAngle += Math.PI;
              }
              ctx.rotate(drawAngle);

              ctx.fillStyle = 'rgba(11, 15, 25, 0.8)';
              ctx.fillRect(-bckgDimensions[0] / 2, -bckgDimensions[1] / 2, bckgDimensions[0], bckgDimensions[1]);

              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
              ctx.fillText(label, 0, 0);
            }
            ctx.restore();
          }}
        />
      </div>

      {/* Floating UI Elements */}
      <div className="absolute top-6 left-6 flex items-center gap-2 bg-surface/80 backdrop-blur-md px-4 py-2 rounded-xl border border-gray-800 shadow-xl">
        <Network className="w-5 h-5 text-primary" />
        <span className="font-semibold text-sm">Tenant Knowledge Graph Explorer</span>
      </div>

      <div className="absolute top-6 right-6 flex gap-2">
        <button className="p-2 bg-surface/80 backdrop-blur-md rounded-lg border border-gray-800 hover:bg-gray-800 transition-colors shadow-lg">
          <Filter className="w-5 h-5" />
        </button>
        <button className="p-2 bg-surface/80 backdrop-blur-md rounded-lg border border-gray-800 hover:bg-gray-800 transition-colors shadow-lg">
          <Maximize2 className="w-5 h-5" />
        </button>
      </div>

      {/* Node Inspector Panel */}
      {selectedNode && (
        <div className="absolute bottom-6 right-6 w-80 bg-surface/90 backdrop-blur-md border border-gray-700 rounded-2xl p-5 shadow-2xl animate-in slide-in-from-bottom-4">
          <div className="flex justify-between items-start mb-4">
            <div>
              <h3 className="text-xl font-bold">{selectedNode.id}</h3>
              <span 
                className="inline-block px-2 py-1 mt-1 rounded text-xs font-bold shadow-sm"
                style={{ backgroundColor: `${getColor(selectedNode.group)}33`, color: getColor(selectedNode.group) }}
              >
                {selectedNode.group}
              </span>
            </div>
            <button onClick={() => setSelectedNode(null)} className="text-gray-500 hover:text-white transition-colors">✕</button>
          </div>
          <div className="space-y-3">
            <div className="bg-gray-900/50 p-3 rounded-lg border border-gray-800 shadow-inner">
              <p className="text-xs text-gray-400 mb-1">Properties</p>
              <div className="text-sm font-mono text-gray-300">
                {'{ tenant_id: "tenant_123", ... }'}
              </div>
            </div>
            <button className="w-full py-2 bg-primary/10 text-primary hover:bg-primary/20 rounded-lg text-sm font-medium transition-colors border border-primary/20 shadow-sm">
              Find Connections
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default GraphCanvas;
