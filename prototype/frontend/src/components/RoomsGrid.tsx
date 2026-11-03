import React from 'react';
import { Categoria, HabitacionConDetalles, RoomStatus } from '../types';
import RoomCard from './RoomCard';

interface RoomsGridProps {
  habitaciones: HabitacionConDetalles[];
  categorias: Categoria[];
  now: number;
  onRoomClick: (habitacion: HabitacionConDetalles) => void;
  onAddConsumo: (habitacion: HabitacionConDetalles) => void;
  onChangeEstado: (habitacion: HabitacionConDetalles, newState: RoomStatus) => void;
}

const RoomsGrid: React.FC<RoomsGridProps> = ({ habitaciones, categorias, now, onRoomClick, onAddConsumo, onChangeEstado }) => (
  <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-4">
    {habitaciones.map((habitacion, orden) => (
      <RoomCard
        key={habitacion.id}
        orden={orden}
        room={habitacion}
        categoria={categorias.find((c) => c.id === habitacion.categoria_id)}
        now={now}
        onClick={onRoomClick}
        onAddConsumo={onAddConsumo}
        onChangeEstado={onChangeEstado}
      />
    ))}
  </div>
);

export default RoomsGrid;
