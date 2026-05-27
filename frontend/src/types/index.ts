export enum TaskStatus {
  PENDING = "PENDING",
  RUNNING = "RUNNING",
  BLOCKED = "BLOCKED",
  COMPLETED = "COMPLETED",
}

export interface DAGNode {
  id: number;
  task_name: string;
  status: TaskStatus;
  dependencies: number[];
  assigned_agent_role: string | null;
  output_data: string | null;
}

export interface ProjectStatusResponse {
  project_id: number;
  is_running: boolean;
  tree: unknown[];
  nodes: DAGNode[];
}
