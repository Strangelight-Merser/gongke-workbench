import {
  Tree,
  TreeItem,
  TreeItemLayout,
  Button,
  Menu,
  MenuTrigger,
  MenuPopover,
  MenuList,
  MenuItem,
} from "@fluentui/react-components";
import {
  DocumentRegular,
  FolderRegular,
  CubeRegular,
  CalculatorRegular,
  AddRegular,
  FolderOpenRegular,
  ArrowSyncRegular,
  DocumentAddRegular,
  MoreHorizontalRegular,
} from "@fluentui/react-icons";
import {
  Project,
  ProjectFile,
  DocumentRef,
  fileGroup,
  cadDocument,
  revisionOf,
} from "./types";
const groups = ["图纸", "模型", "计算", "出图", "报告", "其他文件"];
export function ProjectTree({
  project,
  active,
  open,
  openFile,
  importFiles,
  choose,
  refresh,
  busy,
  splitFile,
}: {
  project: Project | null;
  active: string;
  open(d: DocumentRef): void;
  openFile(f: ProjectFile, preview?: boolean): void;
  choose(create: boolean): void;
  refresh(): void;
  busy: boolean;
  splitFile(file: ProjectFile): void;
  importFiles(): void;
}) {
  return (
    <aside className="project-pane" aria-label="工程树">
      <div className="panel-heading explorer-heading">
        <strong>资源管理器</strong>
        <div className="view-actions">
          <Button
            size="small"
            appearance="subtle"
            icon={<CubeRegular />}
            aria-label="新建模型"
            title="新建模型"
            disabled={!project || busy}
            onClick={() => open(cadDocument)}
          />
          <Button
            size="small"
            appearance="subtle"
            icon={<DocumentAddRegular />}
            aria-label="导入图纸"
            title="导入图纸"
            disabled={!project || busy}
            onClick={importFiles}
          />
          <Button
            size="small"
            appearance="subtle"
            icon={<ArrowSyncRegular />}
            aria-label="刷新工程"
            title="刷新工程"
            disabled={busy}
            onClick={refresh}
          />
          <Menu>
            <MenuTrigger disableButtonEnhancement>
              <Button
                size="small"
                appearance="subtle"
                icon={<MoreHorizontalRegular />}
                aria-label="工程操作"
                title="工程操作"
              />
            </MenuTrigger>
            <MenuPopover>
              <MenuList>
                <MenuItem
                  icon={<AddRegular />}
                  disabled={busy}
                  onClick={() => choose(true)}
                >
                  新建工程
                </MenuItem>
                <MenuItem
                  icon={<FolderOpenRegular />}
                  disabled={busy}
                  onClick={() => choose(false)}
                >
                  打开工程
                </MenuItem>
              </MenuList>
            </MenuPopover>
          </Menu>
        </div>
      </div>
      {project ? (
        <>
          <div className="project-name" title={project.path}>
            <FolderRegular />
            <strong>{project.name}</strong>
          </div>
          <Tree aria-label="工程对象" defaultOpenItems={groups} size="small">
            {groups.map((group) => {
              const files = project.files.filter((f) => fileGroup(f) === group);
              if (group === "其他文件" && !files.length) return null;
              const hasChildren =
                files.length > 0 || ["模型", "计算"].includes(group);
              return (
                <TreeItem
                  key={group}
                  value={group}
                  itemType={hasChildren ? "branch" : "leaf"}
                >
                  <TreeItemLayout
                    iconBefore={<FolderRegular />}
                    aside={
                      !["模型", "计算"].includes(group) ? (
                        <span className="muted">{files.length}</span>
                      ) : undefined
                    }
                  >
                    {group}
                  </TreeItemLayout>
                  {hasChildren && (
                    <Tree>
                      {group === "模型" && (
                        <TreeItem
                          itemType="leaf"
                          value="cad"
                          onClick={() => open(cadDocument)}
                        >
                          <TreeItemLayout
                            iconBefore={<CubeRegular />}
                            className={active === "cad" ? "tree-active" : ""}
                          >
                            原生 CAD
                          </TreeItemLayout>
                        </TreeItem>
                      )}
                      {group === "计算" && (
                        <TreeItem
                          itemType="leaf"
                          value="reducer"
                          onClick={() =>
                            open({
                              id: "reducer",
                              title: "减速器课程设计",
                              type: "reducer",
                            })
                          }
                        >
                          <TreeItemLayout
                            iconBefore={<CalculatorRegular />}
                            className={
                              active === "reducer" ? "tree-active" : ""
                            }
                          >
                            减速器课程设计
                          </TreeItemLayout>
                        </TreeItem>
                      )}
                      {files.map((file) => (
                        <TreeItem
                          key={file.path}
                          value={file.path}
                          itemType="leaf"
                          onClick={() => openFile(file, true)}
                          onDoubleClick={() => openFile(file, false)}
                        >
                          <Menu openOnContext>
                            <MenuTrigger disableButtonEnhancement>
                              <TreeItemLayout
                                iconBefore={
                                  group === "模型" ? (
                                    <CubeRegular />
                                  ) : (
                                    <DocumentRegular />
                                  )
                                }
                                className={
                                  active === file.path ? "tree-active" : ""
                                }
                              >
                                <span title={file.path}>{file.name}</span>
                                {revisionOf(project, file) && (
                                  <span
                                    className="revision-mark"
                                    title={revisionOf(project, file)!.path}
                                  >
                                    {revisionOf(project, file)!
                                      .path.split("/")
                                      .at(-1)}
                                  </span>
                                )}
                                {revisionOf(project, file)?.current ===
                                  false && (
                                  <span className="stale-mark">过期</span>
                                )}
                              </TreeItemLayout>
                            </MenuTrigger>
                            <MenuPopover>
                              <MenuList>
                                <MenuItem
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    openFile(file, false);
                                  }}
                                >
                                  打开并保留
                                </MenuItem>
                                <MenuItem
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    splitFile(file);
                                  }}
                                >
                                  在右侧打开
                                </MenuItem>
                                <MenuItem
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    void navigator.clipboard.writeText(
                                      file.path,
                                    );
                                  }}
                                >
                                  复制相对路径
                                </MenuItem>
                              </MenuList>
                            </MenuPopover>
                          </Menu>
                        </TreeItem>
                      ))}
                    </Tree>
                  )}
                </TreeItem>
              );
            })}
          </Tree>
        </>
      ) : (
        <div className="pane-empty">
          <p>尚未打开工程</p>
          <Button
            appearance="primary"
            disabled={busy}
            onClick={() => choose(false)}
          >
            打开工程
          </Button>
          <Button
            appearance="transparent"
            disabled={busy}
            onClick={() => choose(true)}
          >
            新建工程
          </Button>
        </div>
      )}
    </aside>
  );
}
