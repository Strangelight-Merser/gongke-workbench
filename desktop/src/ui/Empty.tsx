import { Button } from "./controls";
export function Empty({
  title,
  body,
  action,
  onAction,
}: {
  title: string;
  body: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="empty">
      <h2>{title}</h2>
      <p>{body}</p>
      {action && (
        <Button appearance="primary" onClick={onAction}>
          {action}
        </Button>
      )}
    </div>
  );
}
