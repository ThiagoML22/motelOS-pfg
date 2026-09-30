import React from 'react';
import { HabitacionConDetalles, RoomStatus } from '../types';
import RoomCard from './RoomCard';

interface RoomsGridProps {
  habitaciones: HabitacionConDetalles[];
  now: number;
  onRoomClick: (habitacion: HabitacionConDetalles) => void;
  onAddConsumo: (habitacion: HabitacionConDetalles) => void;
  onChangeEstado: (habitacion: HabitacionConDetalles, newState: RoomStatus) => void;
}

const RoomsGrid: React.FC<RoomsGridProps> = ({ habitaciones, now, onRoomClick, onAddConsumo, onChangeEstado }) => (
  <div className="grid animate-fade-in grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-4">
    {habitaciones.map((habitacion) => (
      <RoomCard
        key={habitacion.id}
        room={habitacion}
        now={now}
        onClick={onRoomClick}
        onAddConsumo={onAddConsumo}
        onChangeEstado={onChangeEstado}
      />
    ))}
  </div>
);

export default RoomsGrid;
