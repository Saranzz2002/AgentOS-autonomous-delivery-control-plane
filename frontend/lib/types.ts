export type RepositoryMetadata = {
  name: string;
  repository_url: string;
  branch: string | null;
  commit_sha: string | null;
  language: string;
  languages: Record<string, number>;
  framework: string;
  package_manager: string;
  test_framework: string;
  entry_point: string | null;
  important_files: {
    entry_points: string[];
    configuration_files: string[];
    test_directories: string[];
    documentation: string[];
  };
  source_file_count: number;
  test_file_count: number;
  tree: string[];
};

export type FileChange = { path: string; reason: string };
export type Plan = {
  goal: string;
  assumptions: string[];
  files_to_inspect: FileChange[];
  files_to_modify: FileChange[];
  files_to_create: FileChange[];
  implementation_steps: { step: number; description: string }[];
  testing_strategy: string[];
  risks: string[];
  dependencies: string[];
};

export type TaskEvent = {
  id: string;
  name: string;
  agent: string;
  message: string;
  timestamp: string;
};
