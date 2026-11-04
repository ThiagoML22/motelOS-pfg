import React, { useCallback, useEffect, useState } from 'react';
import { CheckCheck, Download, Eye } from 'lucide-react';
import { Actividad, CategoriaActividad } from '../types';
import { api, EVENTO_RECONECTADO, getErrorMessage } from '../services/api';
import { formatDateTime } from '../utils/format';
import Button from './ui/Button';
import { useToast } from './ui/Toast';
import { EsqueletoTabla } from './ui/Carga';

const CATEGORIAS: { id: CategoriaActividad; label: string }[] = [
  { id: 'INVENTARIO', label: 'Inventario' },
  { id: 'TARIFA', label: 'Tarifa' },
  { id: 'CAJA', label: 'Caja' },
  { id: 'HABITACION', label: 'Habitaciones' },
  { id: 'PERSONAL', label: 'Personal' },
  { id: 'ESTABLECIMIENTO', label: 'Establecimiento' },
  { id: 'PERFIL', label: 'Perfil' },
  { id: 'OPERACION', label: 'Operación' },
];
const ETIQUETA = Object.fromEntries(CATEGORIAS.map((c) => [c.id, c.label])) as Record<CategoriaActividad, string>;

interface ActividadViewProps {
  onCambioPendientes: (pendientes: number) => void;
}

// Registro de actividad (migración 007): quién cambió qué del inventario y de la configuración. Lo que carga un
// conserje (alta de un artículo, reposición de stock) queda «por revisar» hasta que la gerencia lo marca como visto.
const ActividadView: React.FC<ActividadViewProps> = ({ onCambioPendientes }) => {
  const { toast } = useToast();
  const [entradas, setEntradas] = useState<Actividad[]>([]);
  const [estado, setEstado] = useState<'cargando' | 'ok' | 'error'>('cargando');
  const [soloPendientes, setSoloPendientes] = useState(false);
  const [categoria, setCategoria] = useState<CategoriaActividad | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const [lista, pendientes] = await Promise.all([
        api.getActividad({ categoria: categoria ?? undefined, pendientes: soloPendientes || undefined }),
        api.getActividadPendiente(),
      ]);
      setEntradas(lista);
      onCambioPendientes(pendientes);
      setEstado('ok');
    } catch (err) {
      setEstado('error');
      toast(getErrorMessage(err, 'No se pudo cargar el registro de actividad.'), 'error');
    }
  }, [categoria, soloPendientes, onCambioPendientes, toast]);

  useEffect(() => {
    void cargar();
    const alReconectar = () => void cargar();
    window.addEventListener(EVENTO_RECONECTADO, alReconectar);
    return () => window.removeEventListener(EVENTO_RECONECTADO, alReconectar);
  }, [cargar]);

  const revisar = async (ids?: number[]) => {
    setOcupado(true);
    try {
      const quedan = await api.revisarActividad(ids);
      onCambioPendientes(quedan);
      toast(ids ? 'Entrada marcada como vista.' : 'Todo lo pendiente quedó marcado como visto.', 'success');
      await cargar();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo marcar como visto.'), 'error');
    } finally {
      setOcupado(false);
    }
  };

  const hayPendientes = entradas.some((e) => e.requiere_revision && !e.revisado_en);

  return (
    <div className="w-full animate-fade-in">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">Actividad</h1>
          <p className="mt-0.5 text-sm text-muted">
            Cambios de inventario y de configuración, con quién los hizo y en qué guardia. Las entradas no se editan ni se
            borran.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => exportarCsv(entradas)} disabled={entradas.length === 0} className="h-11">
            <Download className="h-4 w-4" aria-hidden="true" />
            Exportar CSV
          </Button>
          <Button onClick={() => void revisar()} disabled={ocupado || !hayPendientes} className="h-11">
            <CheckCheck className="h-4 w-4" aria-hidden="true" />
            Marcar todo como visto
          </Button>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-1.5" role="group" aria-label="Filtrar el registro">
        <Filtro activo={soloPendientes} onClick={() => setSoloPendientes((v) => !v)}>
          Por revisar
        </Filtro>
        <span className="mx-1 h-6 w-px bg-line" aria-hidden="true" />
        <Filtro activo={categoria === null} onClick={() => setCategoria(null)}>
          Todas
        </Filtro>
        {CATEGORIAS.map((c) => (
          <Filtro key={c.id} activo={categoria === c.id} onClick={() => setCategoria(categoria === c.id ? null : c.id)}>
            {c.label}
          </Filtro>
        ))}
      </div>

      {estado === 'cargando' && <EsqueletoTabla filas={8} etiqueta="Cargando registro…" />}
      {estado === 'error' && (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-line bg-surface py-16">
          <p className="text-sm text-muted">No se pudo obtener el registro.</p>
          <Button variant="secondary" onClick={() => void cargar()}>
            Reintentar
          </Button>
        </div>
      )}

      {estado === 'ok' && (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[56rem] text-left text-sm">
            <thead>
              <tr className="border-b border-line bg-surface-2 text-xs font-medium uppercase tracking-wide text-subtle">
                <th scope="col" className="px-4 py-2.5">Cuándo</th>
                <th scope="col" className="px-4 py-2.5">Quién</th>
                <th scope="col" className="px-4 py-2.5">Qué</th>
                <th scope="col" className="px-4 py-2.5">Antes → después</th>
                <th scope="col" className="px-4 py-2.5 text-right">Revisión</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {entradas.map((e) => {
                const pendiente = e.requiere_revision && !e.revisado_en;
                return (
                  <tr key={e.id} className={pendiente ? 'bg-warn-soft/40' : ''}>
                    <td className="whitespace-nowrap px-4 py-2.5 tabular-nums text-muted">{formatDateTime(e.creado_en)}</td>
                    <td className="px-4 py-2.5">
                      <span className="font-medium text-ink">{e.operador_nombre}</span>
                      {e.guardia_id && <span className="block text-xs text-subtle">Guardia N.º {e.guardia_id}</span>}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="mr-2 rounded border border-line px-1.5 py-0.5 text-[11px] uppercase tracking-wide text-muted">
                        {ETIQUETA[e.categoria]}
                      </span>
                      <span className="text-ink">{e.descripcion}</span>
                    </td>
                    <td className="px-4 py-2.5 tabular-nums text-muted">
                      {e.valor_anterior || e.valor_nuevo ? (
                        <>
                          {e.valor_anterior ?? '—'} → <span className="text-ink">{e.valor_nuevo ?? '—'}</span>
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-4 py-1.5 text-right">
                      {pendiente ? (
                        <Button variant="secondary" className="h-11" disabled={ocupado} onClick={() => void revisar([e.id])}>
                          <Eye className="h-4 w-4" aria-hidden="true" />
                          Marcar visto
                        </Button>
                      ) : e.revisado_en ? (
                        <span className="text-xs text-libre">
                          Visto por {e.revisado_por_nombre} · {formatDateTime(e.revisado_en)}
                        </span>
                      ) : (
                        <span className="text-xs text-subtle">Hecho por la gerencia</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {entradas.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-muted">
                    {soloPendientes ? 'No hay nada por revisar.' : 'Todavía no hay actividad registrada.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

// Exporta las entradas visibles (con los filtros aplicados) a un CSV que abre Excel: separador «;» y BOM UTF-8 para que
// respete las tildes.
const exportarCsv = (entradas: Actividad[]) => {
  const celda = (valor: unknown) => `"${String(valor ?? '').replace(/"/g, '""')}"`;
  const filas = [
    ['Fecha', 'Quién', 'Guardia', 'Categoría', 'Acción', 'Descripción', 'Antes', 'Después', 'Revisión'],
    ...entradas.map((e) => [
      formatDateTime(e.creado_en),
      e.operador_nombre,
      e.guardia_id ?? '',
      ETIQUETA[e.categoria],
      e.accion,
      e.descripcion,
      e.valor_anterior,
      e.valor_nuevo,
      e.revisado_en ? `Visto por ${e.revisado_por_nombre}` : e.requiere_revision ? 'Por revisar' : 'Gerencia',
    ]),
  ];
  const texto = '﻿' + filas.map((f) => f.map(celda).join(';')).join('\r\n');
  const url = URL.createObjectURL(new Blob([texto], { type: 'text/csv;charset=utf-8' }));
  const enlace = document.createElement('a');
  enlace.href = url;
  enlace.download = `actividad-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

const Filtro: React.FC<{ activo: boolean; onClick: () => void; children: React.ReactNode }> = ({
  activo,
  onClick,
  children,
}) => (
  <button
    type="button"
    aria-pressed={activo}
    onClick={onClick}
    className={`press hit h-11 rounded-md border px-3 text-sm ${
      activo ? 'border-accent bg-accent-soft font-medium text-accent' : 'border-line-strong bg-surface text-muted hover:text-ink'
    }`}
  >
    {children}
  </button>
);

export default ActividadView;
