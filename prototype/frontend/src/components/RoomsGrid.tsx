import React from 'react';
import { Categoria, HabitacionConDetalles, PedidoVentanilla, RoomStatus } from '../types';
import RoomCard from './RoomCard';

interface RoomsGridProps {
  habitaciones: HabitacionConDetalles[];
  categorias: Categoria[];
  now: number;
  onRoomClick: (habitacion: HabitacionConDetalles) => void;
  onAddConsumo: (habitacion: HabitacionConDetalles) => void;
  onChangeEstado: (habitacion: HabitacionConDetalles, newState: RoomStatus) => void;
  // Lo que pidieron los clientes con su QR y todavía espera.
  pedidos: PedidoVentanilla[];
}

const RoomsGrid: React.FC<RoomsGridProps> = ({ habitaciones, categorias, now, onRoomClick, onAddConsumo, onChangeEstado, pedidos }) => (
  <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-4">
    {/* La entrada escalonada va en una envoltura: la tarjeta queda libre para su propio destello. */}
    {habitaciones.map((habitacion, orden) => (
      <div key={habitacion.id} className="animate-tarjeta-in" style={{ animationDelay: `${Math.min(orden * 28, 420)}ms` }}>
        <RoomCard
          room={habitacion}
          categoria={categorias.find((c) => c.id === habitacion.categoria_id)}
          now={now}
          onClick={onRoomClick}
          onAddConsumo={onAddConsumo}
          onChangeEstado={onChangeEstado}
          pedidos={pedidos.filter((p) => p.habitacion_id === habitacion.id)}
        />
      </div>
    ))}
  </div>
);

export default RoomsGrid;
