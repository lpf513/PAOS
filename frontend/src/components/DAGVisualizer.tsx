import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";

import { TaskStatus, type DAGNode } from "../types";

interface DAGVisualizerProps {
  nodes: DAGNode[];
}

const statusStyles: Record<
  TaskStatus,
  {
    label: string;
    badgeClassName: string;
    nodeClassName: string;
    edgeColor: string;
  }
> = {
  [TaskStatus.COMPLETED]: {
    label: "COMPLETED",
    badgeClassName: "bg-emerald-400/15 text-emerald-300 ring-emerald-300/30",
    nodeClassName: "border-emerald-400/40 bg-emerald-950/30",
    edgeColor: "#34d399",
  },
  [TaskStatus.RUNNING]: {
    label: "RUNNING",
    badgeClassName: "bg-cyan-400/15 text-cyan-300 ring-cyan-300/30",
    nodeClassName: "border-cyan-400/50 bg-cyan-950/30 shadow-cyan-950/40",
    edgeColor: "#22d3ee",
  },
  [TaskStatus.BLOCKED]: {
    label: "BLOCKED",
    badgeClassName: "bg-rose-400/15 text-rose-300 ring-rose-300/30",
    nodeClassName: "border-rose-400/50 bg-rose-950/30",
    edgeColor: "#fb7185",
  },
  [TaskStatus.PENDING]: {
    label: "PENDING",
    badgeClassName: "bg-slate-400/10 text-slate-300 ring-slate-300/20",
    nodeClassName: "border-slate-700 bg-slate-900/90",
    edgeColor: "#64748b",
  },
};

function buildNodeLevels(dagNodes: DAGNode[]): Map<number, number> {
  const byId = new Map(dagNodes.map((node) => [node.id, node]));
  const levelCache = new Map<number, number>();

  const resolveLevel = (node: DAGNode, visiting = new Set<number>()): number => {
    const cachedLevel = levelCache.get(node.id);
    if (cachedLevel !== undefined) {
      return cachedLevel;
    }

    if (visiting.has(node.id)) {
      return 0;
    }

    visiting.add(node.id);
    const parentLevels = node.dependencies
      .map((dependencyId) => byId.get(dependencyId))
      .filter((parent): parent is DAGNode => Boolean(parent))
      .map((parent) => resolveLevel(parent, visiting));

    visiting.delete(node.id);

    const level = parentLevels.length > 0 ? Math.max(...parentLevels) + 1 : 0;
    levelCache.set(node.id, level);
    return level;
  };

  dagNodes.forEach((node) => resolveLevel(node));
  return levelCache;
}

function createNodeLabel(node: DAGNode) {
  const style = statusStyles[node.status];

  return (
    <div
      className={`min-w-[220px] rounded-2xl border px-4 py-3 text-left shadow-xl ${style.nodeClassName}`}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <span
          className={`rounded-full px-2.5 py-1 text-[10px] font-bold tracking-[0.18em] ring-1 ${style.badgeClassName}`}
        >
          {style.label}
        </span>
        <span className="text-[11px] text-slate-500">#{node.id}</span>
      </div>

      <div className="text-sm font-semibold leading-5 text-slate-100">{node.task_name}</div>

      <div className="mt-3 rounded-xl bg-slate-950/50 px-3 py-2 text-xs text-slate-400">
        {node.assigned_agent_role || "未分配代理角色"}
      </div>
    </div>
  );
}

function convertDagToFlow(dagNodes: DAGNode[]): { flowNodes: Node[]; flowEdges: Edge[] } {
  const nodeLevels = buildNodeLevels(dagNodes);
  const rowsByLevel = new Map<number, number>();

  const flowNodes: Node[] = dagNodes.map((node) => {
    const level = nodeLevels.get(node.id) ?? 0;
    const row = rowsByLevel.get(level) ?? 0;
    rowsByLevel.set(level, row + 1);

    return {
      id: String(node.id),
      type: "default",
      position: {
        x: level * 320,
        y: row * 170,
      },
      data: {
        label: createNodeLabel(node),
      },
      draggable: true,
    };
  });

  const nodeIds = new Set(dagNodes.map((node) => node.id));
  const flowEdges: Edge[] = dagNodes.flatMap((node) =>
    node.dependencies
      .filter((dependencyId) => nodeIds.has(dependencyId))
      .map((dependencyId) => ({
        id: `${dependencyId}-${node.id}`,
        source: String(dependencyId),
        target: String(node.id),
        animated: node.status === TaskStatus.RUNNING,
        style: {
          stroke: statusStyles[node.status].edgeColor,
          strokeWidth: 2,
        },
      })),
  );

  return { flowNodes, flowEdges };
}

export default function DAGVisualizer({ nodes }: DAGVisualizerProps) {
  const { flowNodes, flowEdges } = convertDagToFlow(nodes);

  if (nodes.length === 0) {
    return (
      <div className="flex h-full min-h-[360px] items-center justify-center rounded-3xl border border-dashed border-slate-700 bg-slate-900/40 text-sm text-slate-500">
        暂无 DAG 节点数据
      </div>
    );
  }

  return (
    <div className="h-full min-h-[420px] overflow-hidden rounded-3xl border border-slate-800 bg-slate-950/60">
      <ReactFlow
        edges={flowEdges}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        nodes={flowNodes}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#334155" gap={24} />
        <Controls className="!border-slate-700 !bg-slate-900 !text-slate-200" />
        <MiniMap
          maskColor="rgba(15, 23, 42, 0.72)"
          nodeColor={(node) => {
            const dagNode = nodes.find((item) => String(item.id) === node.id);
            return dagNode ? statusStyles[dagNode.status].edgeColor : "#64748b";
          }}
          pannable
          zoomable
        />
      </ReactFlow>
    </div>
  );
}
