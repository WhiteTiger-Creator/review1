export type BusEvent = { kind: string; detail: string };

export function emit(events: BusEvent[], kind: string, detail: string): void {
  events.push({ kind, detail });
}
