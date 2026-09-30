/**
 * Transitions between whole views (#47 visual revision).
 *
 * Page changes, Settings section changes, theme changes and closing a drawer
 * or dialog run inside a View Transition, so the old view is a still image
 * that leaves while the new one arrives: nothing old stays mounted, no effect
 * or request runs twice, and focus and scroll are handled by the update
 * itself. Without browser support, or when motion is reduced, the update
 * simply runs. The CSS for each kind is in motion.css.
 */
import {flushSync} from 'react-dom';

export type TransitionKind = 'page' | 'section' | 'dismiss' | 'theme';
export type Direction = 'forward' | 'back';

type TransitionDocument = Document & {startViewTransition?: (update: () => void) => {finished: Promise<void>}};

export function motionReduced(): boolean {
  if (typeof document === 'undefined') return true;
  return document.documentElement.dataset.motion === 'reduced'
    || Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

export function supportsViewTransitions(): boolean {
  return typeof document !== 'undefined' && typeof (document as TransitionDocument).startViewTransition === 'function';
}

let current = 0;

/**
 * Run `update` exactly once, animated when possible, then `after` once the
 * new view is in the DOM (to move focus into it). A transition started while
 * another runs replaces it; the earlier update still applies.
 */
export function transition(kind: TransitionKind, update: () => void, direction: Direction = 'forward', after?: () => void): void {
  const doc = document as TransitionDocument;
  if (!supportsViewTransitions() || motionReduced() || document.visibilityState !== 'visible') {
    update();
    if (after) requestAnimationFrame(after);
    return;
  }
  const root = document.documentElement;
  const ticket = ++current;
  root.dataset.vt = kind;
  root.dataset.vtDirection = direction;
  let ran = false;
  const apply = () => { if (!ran) { ran = true; flushSync(update); after?.(); } };
  try {
    doc.startViewTransition!(apply).finished.catch(() => {}).finally(() => {
      if (ticket === current) { delete root.dataset.vt; delete root.dataset.vtDirection; }
    });
  } catch {
    delete root.dataset.vt; delete root.dataset.vtDirection;
    apply();
  }
}

/** Which way a move between two positions in an ordered list goes. */
export function directionBetween(order: readonly string[], from: string, to: string): Direction {
  const a = order.indexOf(from), b = order.indexOf(to);
  return a >= 0 && b >= 0 && b < a ? 'back' : 'forward';
}
