import { Info } from 'lucide-react';
import { ICON } from './icon';

export const RESEARCH_NOTICE = 'Research prototype. Not a medical device. Do not use it to make treatment decisions.';

export function Wordmark({ large = false }: { large?: boolean }) {
  return (
    <span className={`wordmark${large ? ' wordmark-large' : ''}`}>
      <span className="wordmark-name">GlucoRAG</span>
      <span className="wordmark-sub">Your next hour of glucose</span>
    </span>
  );
}

export function ResearchNotice({ className = '' }: { className?: string }) {
  return (
    <p className={`notice ${className}`.trim()}>
      <Info {...ICON} />
      {RESEARCH_NOTICE}
    </p>
  );
}
