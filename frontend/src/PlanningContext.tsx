import { createContext, useContext, useState, type ReactNode } from 'react';
import type { CompletedRun, SimulationRequest } from './api/simulation';
import type { LabSlot, SlotId, Toss, OptimizerSettings, PlanSide } from './domain/lab';
import type { OptimizationRun } from './api/lab';

type Slots = Record<SlotId, LabSlot>;
interface PlanningStore {
  slots: Slots | null;
  initialize: (slots: Slots) => void;
  edit: (id: SlotId, request: SimulationRequest, toss?: Toss, venueName?: string) => void;
  complete: (id: SlotId, run: CompletedRun) => void;
  copy: (from: SlotId, to: SlotId) => void;
  load: (id: SlotId, slot: LabSlot) => void;
  active: SlotId;
  setActive: (id: SlotId) => void;
  side: PlanSide;
  setSide: (side: PlanSide) => void;
  settings: OptimizerSettings | null;
  setSettings: (value: OptimizerSettings) => void;
  optimization: OptimizationRun | null;
  setOptimization: (value: OptimizationRun) => void;
}
const PlanningContext = createContext<PlanningStore | null>(null);
export function PlanningProvider({ children }: { children: ReactNode }) {
  const [slots, setSlots] = useState<Slots | null>(null);
  const [active, setActive] = useState<SlotId>('A'),
    [side, setSide] = useState<PlanSide>('team_a'),
    [settings, setSettings] = useState<OptimizerSettings | null>(null),
    [optimization, setOptimization] = useState<OptimizationRun | null>(null);
  return (
    <PlanningContext.Provider
      value={{
        slots,
        active,
        setActive,
        side,
        setSide,
        settings,
        setSettings,
        optimization,
        setOptimization,
        initialize: (initial) => setSlots((previous) => previous ?? initial),
        edit: (id, request, toss, venueName) =>
          setSlots((previous) =>
            previous
              ? {
                  ...previous,
                  [id]: {
                    ...previous[id],
                    request,
                    toss: toss ?? previous[id].toss,
                    venueName: venueName ?? previous[id].venueName,
                  },
                }
              : previous,
          ),
        complete: (id, run) =>
          setSlots((previous) =>
            previous ? { ...previous, [id]: { ...previous[id], run } } : previous,
          ),
        copy: (from, to) =>
          setSlots((previous) =>
            previous
              ? { ...previous, [to]: { ...structuredClone(previous[from]), run: null } }
              : previous,
          ),
        load: (id, slot) =>
          setSlots((previous) =>
            previous
              ? { ...previous, [id]: slot }
              : {
                  A: { ...structuredClone(slot), run: id === 'A' ? slot.run : null },
                  B: { ...structuredClone(slot), run: id === 'B' ? slot.run : null },
                },
          ),
      }}
    >
      {children}
    </PlanningContext.Provider>
  );
}
export function usePlanning() {
  const value = useContext(PlanningContext);
  if (!value) throw new Error('PlanningProvider is required');
  return value;
}
