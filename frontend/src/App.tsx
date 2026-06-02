import { FormEvent, useEffect, useMemo, useState } from "react";
import { AlertCircle, Bot, FolderKanban, Loader2, Play, Plus, X } from "lucide-react";

import AgentTerminal from "./components/AgentTerminal";
import DAGVisualizer from "./components/DAGVisualizer";
import "./App.css";
import {
  createProject,
  getProjectStatus,
  startProject,
} from "./services/api";
import type { DAGNode, ProjectStatusResponse } from "./types";

interface ProjectItem {
  id: number;
  name: string;
}

const POLLING_INTERVAL_MS = 2000;

function App() {
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<number | null>(null);
  const [projectStatus, setProjectStatus] = useState<ProjectStatusResponse | null>(null);
  const [dagNodes, setDagNodes] = useState<DAGNode[]>([]);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [rawContent, setRawContent] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const currentProject = useMemo(
    () => projects.find((project) => project.id === currentProjectId) ?? null,
    [currentProjectId, projects],
  );

  const syncProjectStatus = async (projectId: number) => {
    const status = await getProjectStatus(projectId);
    setProjectStatus(status);
    setDagNodes(status.nodes);
    return status;
  };

  useEffect(() => {
    if (!currentProjectId || !projectStatus?.is_running) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      syncProjectStatus(currentProjectId).catch((error: unknown) => {
        setErrorMessage(error instanceof Error ? error.message : "同步项目状态失败");
      });
    }, POLLING_INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, [currentProjectId, projectStatus?.is_running]);

  const handleCreateProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);
    setIsCreating(true);

    try {
      const createdProject = await createProject(projectName.trim(), rawContent.trim());
      const nextProject = {
        id: createdProject.project_id,
        name: projectName.trim(),
      };

      setProjects((currentProjects) => [nextProject, ...currentProjects]);
      setCurrentProjectId(createdProject.project_id);
      setProjectStatus(null);
      setDagNodes([]);
      setProjectName("");
      setRawContent("");
      setIsCreateModalOpen(false);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "创建项目失败");
    } finally {
      setIsCreating(false);
    }
  };

  const handleStartProject = async () => {
    if (!currentProjectId) {
      setErrorMessage("请先创建或选择一个项目。");
      return;
    }

    setErrorMessage(null);
    setIsStarting(true);

    try {
      await startProject(currentProjectId);
      await syncProjectStatus(currentProjectId);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "启动代理实例失败");
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-gray-900 text-white">
      <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-gray-800 bg-gray-950">
        <div className="border-b border-gray-800 p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-500/15 text-cyan-300 ring-1 ring-cyan-400/30">
              <Bot size={24} />
            </div>
            <div className="min-w-0">
              <h1 className="text-lg font-bold tracking-wide">PAOS</h1>
              <p className="text-xs uppercase tracking-[0.22em] text-gray-500">Agent OS</p>
            </div>
          </div>

          <button
            className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 px-4 py-3 text-sm font-bold text-gray-950 shadow-lg shadow-cyan-950/40 transition hover:bg-cyan-300 active:scale-[0.99]"
            onClick={() => setIsCreateModalOpen(true)}
            type="button"
          >
            <Plus size={18} />
            新建项目
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">
            <FolderKanban size={14} />
            项目列表
          </div>

          {projects.length === 0 ? (
            <div className="rounded-xl border border-dashed border-gray-800 p-4 text-center text-sm text-gray-500">
              暂无项目
            </div>
          ) : (
            <div className="space-y-2">
              {projects.map((project) => {
                const isSelected = project.id === currentProjectId;

                return (
                  <button
                    className={`w-full rounded-xl border p-3 text-left transition ${
                      isSelected
                        ? "border-cyan-400/50 bg-cyan-400/10"
                        : "border-gray-800 bg-gray-900 hover:border-gray-700 hover:bg-gray-800"
                    }`}
                    key={project.id}
                    onClick={() => {
                      setCurrentProjectId(project.id);
                      setProjectStatus(null);
                      setDagNodes([]);
                    }}
                    type="button"
                  >
                    <div className="truncate text-sm font-semibold">{project.name}</div>
                    <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
                      <span
                        className={`h-2 w-2 rounded-full ${
                          isSelected && projectStatus?.is_running ? "bg-cyan-300" : "bg-gray-600"
                        }`}
                      />
                      {isSelected && projectStatus?.is_running ? "运行中" : "待启动"}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col bg-gray-900">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-gray-800 bg-gray-950/70 px-6">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
              当前项目
            </p>
            <h2 className="truncate text-lg font-bold text-white">
              {currentProject?.name ?? "尚未选择项目"}
            </h2>
          </div>

          <button
            className="flex items-center gap-2 rounded-lg bg-indigo-500 px-4 py-2 text-sm font-bold text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-gray-700 disabled:text-gray-400"
            disabled={!currentProjectId || isStarting}
            onClick={handleStartProject}
            type="button"
          >
            {isStarting ? <Loader2 className="animate-spin" size={17} /> : <Play size={17} />}
            启动代理呼叫
          </button>
        </header>

        {errorMessage && (
          <div className="mx-6 mt-4 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-950/40 px-4 py-3 text-sm text-red-200">
            <AlertCircle size={16} />
            {errorMessage}
          </div>
        )}

        <section className="min-h-0 flex-1 p-4">
          <div className="h-full min-h-0 overflow-hidden rounded-2xl border border-gray-800 bg-gray-950/60">
            <DAGVisualizer nodes={dagNodes} />
          </div>
        </section>

        <section className="h-80 shrink-0 border-t border-gray-800 bg-black p-4">
          <AgentTerminal />
        </section>
      </main>

      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <form
            className="w-full max-w-2xl rounded-2xl border border-gray-800 bg-gray-950 p-6 shadow-2xl"
            onSubmit={handleCreateProject}
          >
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-bold text-white">新建项目</h2>
                <p className="mt-1 text-sm text-gray-500">
                  输入项目名称和业务原始需求，PAOS 会创建项目并解析约束。
                </p>
              </div>
              <button
                className="rounded-lg p-2 text-gray-500 transition hover:bg-gray-900 hover:text-white"
                onClick={() => setIsCreateModalOpen(false)}
                type="button"
              >
                <X size={20} />
              </button>
            </div>

            <label className="block text-sm font-semibold text-gray-300" htmlFor="project-name">
              项目名称
            </label>
            <input
              className="mt-2 w-full rounded-lg border border-gray-700 bg-gray-900 px-4 py-3 text-sm text-white outline-none transition placeholder:text-gray-600 focus:border-cyan-400"
              id="project-name"
              onChange={(event) => setProjectName(event.currentTarget.value)}
              placeholder="例如：智能客服体验优化"
              required
              value={projectName}
            />

            <label className="mt-5 block text-sm font-semibold text-gray-300" htmlFor="raw-content">
              业务原始需求
            </label>
            <textarea
              className="mt-2 h-52 w-full resize-none rounded-lg border border-gray-700 bg-gray-900 px-4 py-3 text-sm leading-6 text-white outline-none transition placeholder:text-gray-600 focus:border-cyan-400"
              id="raw-content"
              onChange={(event) => setRawContent(event.currentTarget.value)}
              placeholder="粘贴业务文档、约束、目标、合规要求等原始文本..."
              required
              value={rawContent}
            />

            <div className="mt-6 flex justify-end gap-3">
              <button
                className="rounded-lg border border-gray-700 px-4 py-2 text-sm font-bold text-gray-300 transition hover:bg-gray-900"
                onClick={() => setIsCreateModalOpen(false)}
                type="button"
              >
                取消
              </button>
              <button
                className="flex items-center gap-2 rounded-lg bg-cyan-400 px-4 py-2 text-sm font-bold text-gray-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-gray-700 disabled:text-gray-400"
                disabled={isCreating || !projectName.trim() || !rawContent.trim()}
                type="submit"
              >
                {isCreating && <Loader2 className="animate-spin" size={16} />}
                创建项目
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

export default App;
