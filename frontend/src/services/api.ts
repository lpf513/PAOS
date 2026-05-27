import axios from "axios";

import type { ProjectStatusResponse } from "../types";

const api = axios.create({
  baseURL: "http://127.0.0.1:8000",
  headers: {
    "Content-Type": "application/json",
  },
});

export interface CreateProjectResponse {
  project_id: number;
}

export interface StartProjectResponse {
  project_id: number;
  status: "started" | "already_running";
}

export async function createProject(
  name: string,
  rawContent: string,
): Promise<CreateProjectResponse> {
  const response = await api.post<CreateProjectResponse>("/api/projects/create", {
    name,
    raw_content: rawContent,
  });

  return response.data;
}

export async function startProject(projectId: number): Promise<StartProjectResponse> {
  const response = await api.post<StartProjectResponse>(`/api/projects/${projectId}/start`);

  return response.data;
}

export async function getProjectStatus(projectId: number): Promise<ProjectStatusResponse> {
  const response = await api.get<ProjectStatusResponse>(`/api/projects/${projectId}/status`);

  return response.data;
}

export default api;
