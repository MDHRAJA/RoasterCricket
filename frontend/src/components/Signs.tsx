import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { team } from '../domain/teams';

export function RouteBullet({ id, small = false }: { id: string; small?: boolean }) {
  const t = team(id);
  return (
    <span
      className={`route-bullet ${small ? 'small' : ''}`}
      style={{ '--team': t.color, '--team-ink': t.ink } as CSSProperties}
      aria-label={t.name}
    >
      {id}
    </span>
  );
}

export type IconName =
  | 'search'
  | 'arrow'
  | 'close'
  | 'sun'
  | 'moon'
  | 'stumps'
  | 'bat'
  | 'ball'
  | 'helmet'
  | 'glove'
  | 'boundary'
  | 'dew'
  | 'pitch'
  | 'toss';
const shapes: Record<IconName, ReactNode> = {
  search: (
    <>
      <path
        fillRule="evenodd"
        d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm0 3a5 5 0 1 1 0 10 5 5 0 0 1 0-10Z"
      />
      <path d="m15 13 8 8-2 2-8-8Z" />
    </>
  ),
  arrow: <path d="M2 10h13l-5-5 2-2 10 9-10 9-2-2 5-6H2Z" />,
  close: <path d="m5 3 7 7 7-7 2 2-7 7 7 7-2 2-7-7-7 7-2-2 7-7-7-7Z" />,
  sun: (
    <>
      <circle cx="12" cy="12" r="5" />
      <path d="M11 0h2v4h-2zm0 20h2v4h-2zM0 11h4v2H0zm20 0h4v2h-4zM3 4l1-1 3 3-1 1zm14 14 1-1 3 3-1 1zM3 20l3-3 1 1-3 3zM17 6l3-3 1 1-3 3Z" />
    </>
  ),
  moon: <path d="M15 2A10 10 0 1 0 22 16 9 9 0 0 1 15 2Z" />,
  stumps: <path d="M5 7h3v15H5zm6 0h3v15h-3zm6 0h3v15h-3zM4 3h9v3H4zm10 0h7v3h-7Z" />,
  bat: <path d="m15 1 3 2-5 8 2 2-7 10-6-4 7-10 2 1Z" />,
  ball: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path fill="var(--icon-cut, var(--panel))" d="M4 6h2l14 12-2 1Zm-1 4 1-2 13 12-2 1Z" />
    </>
  ),
  helmet: <path d="M2 13V9a9 9 0 0 1 18 0v4h-9v3h9v-2h2v8H10v-3H2Zm11 6v1h7v-1Z" />,
  glove: (
    <path d="M5 11V4a1.5 1.5 0 0 1 3 0v7h1V2a1.5 1.5 0 0 1 3 0v9h1V3a1.5 1.5 0 0 1 3 0v8h1V6a1.5 1.5 0 0 1 3 0v11l-3 6H7L1 14a2 2 0 0 1 3-2l2 3Z" />
  ),
  boundary: (
    <path
      fillRule="evenodd"
      d="M12 1a11 11 0 1 0 0 22 11 11 0 0 0 0-22Zm0 3a8 8 0 1 1 0 16 8 8 0 0 1 0-16Zm-1 2h2v12h-2Z"
    />
  ),
  dew: (
    <path d="M12 1 4 13a9 9 0 1 0 16 0ZM7 14h2a4 4 0 0 0 4 5v2a6 6 0 0 1-6-7Z" fillRule="evenodd" />
  ),
  pitch: <path fillRule="evenodd" d="M5 1h14v22H5Zm3 3v16h8V4Zm1 2h6v2H9Zm0 10h6v2H9Z" />,
  toss: (
    <>
      <path
        fillRule="evenodd"
        d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 3a7 7 0 1 1 0 14 7 7 0 0 1 0-14Z"
      />
      <path d="M11 7h2v10h-2zM9 9h6v2H9Z" />
    </>
  ),
};
export function Icon({ name, className = '' }: { name: IconName; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="24"
      height="24"
      fill="currentColor"
      className={className}
      aria-hidden="true"
    >
      {shapes[name]}
    </svg>
  );
}

export function TagToggle({
  active,
  children,
  onClick,
  ...props
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
  'aria-expanded'?: boolean;
  'aria-controls'?: string;
  disabled?: boolean;
}) {
  return (
    <button className="tag-toggle" aria-pressed={active} onClick={onClick} {...props}>
      {children}
    </button>
  );
}
export function ServiceNote({ children }: { children: ReactNode }) {
  return (
    <p className="service-note">
      <span aria-hidden="true">i</span>
      {children}
    </p>
  );
}
export function SignPanel({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`sign-panel ${className}`}>{children}</section>;
}

export function SplitFlap({ value, label }: { value: string; label?: string }) {
  const [previous, setPrevious] = useState(value);
  const old = useRef(value);
  const [flipping, setFlipping] = useState(false);
  useEffect(() => {
    if (old.current === value) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    setPrevious(old.current);
    old.current = value;
    setFlipping(!reduced);
    const timer = window.setTimeout(
      () => {
        setPrevious(value);
        setFlipping(false);
      },
      reduced ? 0 : 420,
    );
    return () => window.clearTimeout(timer);
  }, [value]);
  const width = Math.max(value.length, previous.length);
  const current = value.padStart(width, ' ');
  const before = previous.padStart(width, ' ');
  return (
    <span className="split-flap" role="img" aria-label={label || value}>
      {[...current].map((char, index) => (
        <span
          key={index}
          className={`flap-cell ${flipping && before[index] !== char ? 'flipping' : ''}`}
          style={{ '--delay': `${index * 18}ms` } as CSSProperties}
          aria-hidden="true"
        >
          <span className="flap-half top">
            <span>{char}</span>
          </span>
          <span className="flap-half bottom">
            <span>{before[index]}</span>
          </span>
          <span className="flap-half top outgoing">
            <span>{before[index]}</span>
          </span>
          <span className="flap-half bottom incoming">
            <span>{char}</span>
          </span>
        </span>
      ))}
    </span>
  );
}
