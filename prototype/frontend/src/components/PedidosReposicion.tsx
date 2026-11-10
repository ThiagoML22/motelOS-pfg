import React, { useCallback, useEffect, useState } from 'react';
import { ChevronDown, FileDown, PackageCheck, Plus, ShoppingCart, Trash2 } from 'lucide-react';
import { Articulo, Pedido } from '../types';
import { api, EVENTO_RECONECTADO, getErrorMessage } from '../services/api';
import { formatDateTime } from '../utils/format';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';

// Pedidos de reposición a proveedores (migración 010): la gerencia los arma (puede partir de la reposición sugerida
// por la inteligencia) y los descarga en PDF; cuando llega la mercadería, el conserje o la gerencia los recibe con
// las cantidades reales, que se suman al stock y quedan en el registro de actividad.

const ESTADO = {
  Pendiente: 'bg-warn-soft text-warn',
  Recibido: 'bg-libre-soft text-libre',
  Anulado: 'bg-mant-soft text-mant',
};

const unidades = (pedido: Pedido) => pedido.items.reduce((s, i) => s + i.cantidad, 0);

const descargarPdf = (id: number, avisar: (texto: string) => void) =>
  void api.descargarPedido(id).catch((err) => avisar(getErrorMessage(err, 'No se pudo generar el pedido en PDF.')));

interface SeccionPedidosProps {
  esGerencia: boolean;
  // Avisa a la vista de inventario que el stock cambió (al recibir un pedido).
  onStockCambiado: () => void;
  // Cambia cuando se crea un pedido desde afuera de la sección (el botón «Nuevo pedido» del encabezado).
  version: number;
}

export const SeccionPedidos: React.FC<SeccionPedidosProps> = ({ esGerencia, onStockCambiado, version }) => {
  const { toast } = useToast();
  const [pedidos, setPedidos] = useState<Pedido[]>([]);
  const [recibiendo, setRecibiendo] = useState<Pedido | null>(null);
  const [verCerrados, setVerCerrados] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setPedidos(await api.getPedidos());
    } catch {
      // la lista se vuelve a pedir al reconectar o al próximo cambio
    }
  }, []);

  useEffect(() => {
    void cargar();
    const alReconectar = () => void cargar();
    window.addEventListener(EVENTO_RECONECTADO, alReconectar);
    return () => window.removeEventListener(EVENTO_RECONECTADO, alReconectar);
  }, [cargar, version]);

  const pendientes = pedidos.filter((p) => p.estado === 'Pendiente');
  const cerrados = pedidos.filter((p) => p.estado !== 'Pendiente');
  if (pedidos.length === 0) return null;

  const anular = async (pedido: Pedido) => {
    try {
      await api.anularPedido(pedido.id);
      toast(`Pedido N.º ${pedido.id} anulado.`, 'success');
      await cargar();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo anular el pedido.'), 'error');
    }
  };

  const fila = (p: Pedido) => (
    <li key={p.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2.5 text-sm">
      <span className="font-medium text-ink">Pedido N.º {p.id}</span>
      <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${ESTADO[p.estado]}`}>{p.estado}</span>
      <span className="min-w-0 flex-1 truncate text-muted">
        {p.proveedor ? `${p.proveedor} · ` : ''}
        {p.items.length} artículos · {unidades(p)} u. · {formatDateTime(p.creado_en)}
        {p.cerrado_por_nombre && ` · ${p.estado === 'Recibido' ? 'recibió' : 'anuló'} ${p.cerrado_por_nombre}`}
      </span>
      <span className="flex gap-1.5">
        <Button variant="ghost" size="sm" onClick={() => descargarPdf(p.id, (t) => toast(t, 'error'))} aria-label={`PDF del pedido ${p.id}`}>
          <FileDown className="h-3.5 w-3.5" aria-hidden="true" />
          PDF
        </Button>
        {p.estado === 'Pendiente' && esGerencia && (
          <Button variant="ghost" size="sm" onClick={() => void anular(p)}>
            Anular
          </Button>
        )}
        {p.estado === 'Pendiente' && (
          <Button variant="secondary" size="sm" onClick={() => setRecibiendo(p)}>
            <PackageCheck className="h-3.5 w-3.5" aria-hidden="true" />
            Recibir
          </Button>
        )}
      </span>
    </li>
  );

  return (
    <section className="mb-5 rounded-lg border border-line bg-surface" aria-labelledby="titulo-pedidos">
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-2.5">
        <h2 id="titulo-pedidos" className="flex items-center gap-2 text-sm font-semibold text-ink">
          <ShoppingCart className="h-4 w-4 text-muted" aria-hidden="true" />
          Pedidos a proveedores
          {pendientes.length > 0 && <span className="font-normal text-subtle">· {pendientes.length} por recibir</span>}
        </h2>
        {cerrados.length > 0 && (
          <button
            type="button"
            onClick={() => setVerCerrados((v) => !v)}
            aria-expanded={verCerrados}
            className="press inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-accent hover:bg-accent-soft"
          >
            {verCerrados ? 'Ocultar anteriores' : 'Ver anteriores'}
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${verCerrados ? 'rotate-180' : ''}`} aria-hidden="true" />
          </button>
        )}
      </div>
      <ul className="divide-y divide-line">
        {pendientes.map(fila)}
        {pendientes.length === 0 && <li className="px-3 py-2.5 text-sm text-muted">No hay pedidos por recibir.</li>}
        {verCerrados && cerrados.map(fila)}
      </ul>
      {recibiendo && (
        <RecibirPedidoModal
          pedido={recibiendo}
          onClose={() => setRecibiendo(null)}
          onRecibido={() => {
            setRecibiendo(null);
            void cargar();
            onStockCambiado();
          }}
        />
      )}
    </section>
  );
};

const RecibirPedidoModal: React.FC<{ pedido: Pedido; onClose: () => void; onRecibido: () => void }> = ({
  pedido,
  onClose,
  onRecibido,
}) => {
  const { toast } = useToast();
  const [recibidas, setRecibidas] = useState<Record<number, string>>(() =>
    Object.fromEntries(pedido.items.map((i) => [i.articulo_id, String(i.cantidad)])),
  );
  const [enviando, setEnviando] = useState(false);
  const valido = pedido.items.every((i) => /^\d{1,5}$/.test(recibidas[i.articulo_id] ?? ''));

  const confirmar = async () => {
    setEnviando(true);
    try {
      await api.recibirPedido(
        pedido.id,
        pedido.items.map((i) => ({ articulo_id: i.articulo_id, recibida: Number(recibidas[i.articulo_id]) })),
      );
      toast(`Pedido N.º ${pedido.id} recibido: el stock ya está actualizado.`, 'success');
      onRecibido();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo registrar la recepción.'), 'error');
      setEnviando(false);
    }
  };

  return (
    <Modal
      title={`Recibir el pedido N.º ${pedido.id}`}
      subtitle="Anotá lo que llegó de cada artículo (0 si no vino). Se suma al stock y queda en Actividad."
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={() => void confirmar()} disabled={enviando || !valido}>
            <PackageCheck className="h-4 w-4" aria-hidden="true" />
            {enviando ? 'Guardando…' : 'Confirmar recepción'}
          </Button>
        </div>
      }
    >
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-subtle">
            <th className="py-2 font-medium">Artículo</th>
            <th className="py-2 text-right font-medium">Pedido</th>
            <th className="py-2 text-right font-medium">Llegó</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {pedido.items.map((i) => (
            <tr key={i.articulo_id}>
              <td className="py-2 pr-2 text-ink">
                {i.descripcion}
                <span className="block text-xs text-muted">Stock actual: {i.stock_actual}</span>
              </td>
              <td className="py-2 text-right tabular-nums text-muted">{i.cantidad}</td>
              <td className="py-2 pl-2 text-right">
                <input
                  inputMode="numeric"
                  aria-label={`Unidades recibidas de ${i.descripcion}`}
                  className={`${inputClass} h-10 w-24 text-right tabular-nums`}
                  value={recibidas[i.articulo_id] ?? ''}
                  onChange={(e) => setRecibidas((r) => ({ ...r, [i.articulo_id]: e.target.value.trim() }))}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Modal>
  );
};

interface Linea {
  articulo_id: number;
  cantidad: string;
}

// Alta de un pedido: empieza con la reposición sugerida (lo que falta para dos semanas) y se ajusta a mano.
export const NuevoPedidoModal: React.FC<{ onClose: () => void; onCreado: (pedido: Pedido) => void }> = ({ onClose, onCreado }) => {
  const { toast } = useToast();
  const [articulos, setArticulos] = useState<Articulo[]>([]);
  const [lineas, setLineas] = useState<Linea[]>([]);
  const [proveedor, setProveedor] = useState('');
  const [nota, setNota] = useState('');
  const [agregar, setAgregar] = useState<number | ''>('');
  const [cargando, setCargando] = useState(true);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    Promise.all([api.getArticulos(), api.getPedidoSugerido()])
      .then(([todos, sugerido]) => {
        setArticulos(todos);
        setLineas(sugerido.map((s) => ({ articulo_id: s.articulo_id, cantidad: String(s.sugerido) })));
      })
      .catch((err) => toast(getErrorMessage(err, 'No se pudo cargar la reposición sugerida.'), 'error'))
      .finally(() => setCargando(false));
  }, [toast]);

  const articulo = (id: number) => articulos.find((a) => a.id === id);
  const disponibles = articulos.filter((a) => !lineas.some((l) => l.articulo_id === a.id));
  const valido = lineas.length > 0 && lineas.every((l) => /^\d{1,5}$/.test(l.cantidad) && Number(l.cantidad) > 0);

  const crear = async () => {
    setEnviando(true);
    try {
      const pedido = await api.crearPedido({
        proveedor: proveedor.trim() || undefined,
        nota: nota.trim() || undefined,
        items: lineas.map((l) => ({ articulo_id: l.articulo_id, cantidad: Number(l.cantidad) })),
      });
      toast(`Pedido N.º ${pedido.id} creado. Descargá el PDF para mandárselo al proveedor.`, 'success');
      onCreado(pedido);
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo crear el pedido.'), 'error');
      setEnviando(false);
    }
  };

  return (
    <Modal
      size="lg"
      title="Nuevo pedido a un proveedor"
      subtitle="Empieza con la reposición sugerida (lo que falta para cubrir dos semanas); ajustá lo que quieras."
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={() => void crear()} disabled={enviando || !valido}>
            <ShoppingCart className="h-4 w-4" aria-hidden="true" />
            {enviando ? 'Creando…' : `Crear pedido (${lineas.length} artículos)`}
          </Button>
        </div>
      }
    >
      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <Field label="Proveedor (opcional)" htmlFor="pedido_proveedor">
          <input id="pedido_proveedor" maxLength={80} className={`${inputClass} h-10`} value={proveedor} onChange={(e) => setProveedor(e.target.value)} />
        </Field>
        <Field label="Nota (opcional)" htmlFor="pedido_nota">
          <input id="pedido_nota" maxLength={300} className={`${inputClass} h-10`} value={nota} onChange={(e) => setNota(e.target.value)} />
        </Field>
      </div>
      {cargando ? (
        <p className="py-6 text-center text-sm text-muted">Calculando la reposición sugerida…</p>
      ) : (
        <>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-subtle">
                <th className="py-2 font-medium">Artículo</th>
                <th className="py-2 text-right font-medium">Stock</th>
                <th className="py-2 text-right font-medium">Pedir</th>
                <th className="w-10 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {lineas.map((l) => (
                <tr key={l.articulo_id}>
                  <td className="py-2 pr-2 text-ink">{articulo(l.articulo_id)?.descripcion ?? `Artículo ${l.articulo_id}`}</td>
                  <td className="py-2 text-right tabular-nums text-muted">{articulo(l.articulo_id)?.stock_actual ?? '—'}</td>
                  <td className="py-2 pl-2 text-right">
                    <input
                      inputMode="numeric"
                      aria-label="Unidades a pedir"
                      className={`${inputClass} h-10 w-24 text-right tabular-nums`}
                      value={l.cantidad}
                      onChange={(e) =>
                        setLineas((ls) => ls.map((x) => (x.articulo_id === l.articulo_id ? { ...x, cantidad: e.target.value.trim() } : x)))
                      }
                    />
                  </td>
                  <td className="py-2 text-right">
                    <button
                      type="button"
                      onClick={() => setLineas((ls) => ls.filter((x) => x.articulo_id !== l.articulo_id))}
                      aria-label="Quitar del pedido"
                      className="press hit rounded-md p-1.5 text-muted hover:bg-danger-soft hover:text-danger"
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
              {lineas.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-muted">
                    No hay nada para reponer según las ventas: agregá artículos abajo.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {disponibles.length > 0 && (
            <div className="mt-3 flex items-end gap-2">
              <Field label="Agregar un artículo" htmlFor="pedido_agregar">
                <select
                  id="pedido_agregar"
                  className={`${inputClass} h-10 min-w-[16rem]`}
                  value={agregar}
                  onChange={(e) => setAgregar(e.target.value === '' ? '' : Number(e.target.value))}
                >
                  <option value="">Elegí un artículo…</option>
                  {disponibles.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.descripcion} (stock {a.stock_actual})
                    </option>
                  ))}
                </select>
              </Field>
              <Button
                variant="secondary"
                className="h-10"
                disabled={agregar === ''}
                onClick={() => {
                  if (agregar === '') return;
                  setLineas((ls) => [...ls, { articulo_id: agregar, cantidad: '6' }]);
                  setAgregar('');
                }}
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                Agregar
              </Button>
            </div>
          )}
        </>
      )}
    </Modal>
  );
};

// Botón para abrir el alta de un pedido y descargar su PDF al crearlo (encabezado de Inventario e Inteligencia).
export const BotonNuevoPedido: React.FC<{ onCreado?: () => void; className?: string; etiqueta?: string }> = ({
  onCreado,
  className = '',
  etiqueta = 'Nuevo pedido',
}) => {
  const { toast } = useToast();
  const [abierto, setAbierto] = useState(false);
  return (
    <>
      <Button variant="secondary" className={className} onClick={() => setAbierto(true)}>
        <ShoppingCart className="h-4 w-4" aria-hidden="true" />
        {etiqueta}
      </Button>
      {abierto && (
        <NuevoPedidoModal
          onClose={() => setAbierto(false)}
          onCreado={(pedido) => {
            setAbierto(false);
            descargarPdf(pedido.id, (t) => toast(t, 'error'));
            onCreado?.();
          }}
        />
      )}
    </>
  );
};
