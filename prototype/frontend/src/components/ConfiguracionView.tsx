import React, { useCallback, useEffect, useState } from 'react';
import { BedDouble, Coins, Package, Receipt, Users } from 'lucide-react';
import { Articulo, FondoCambio, HabitacionConfiguracion, OperadorEstado, Tarifa } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime, formatMoney, formatRoomNumber } from '../utils/format';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';

type Seccion = 'tarifa' | 'fondo' | 'articulos' | 'habitaciones' | 'conserjes';

const SECCIONES: { id: Seccion; label: string; icon: React.ElementType }[] = [
  { id: 'tarifa', label: 'Tarifa', icon: Receipt },
  { id: 'fondo', label: 'Fondo de cambio', icon: Coins },
  { id: 'articulos', label: 'Artículos', icon: Package },
  { id: 'habitaciones', label: 'Habitaciones', icon: BedDouble },
  { id: 'conserjes', label: 'Conserjes', icon: Users },
];

// RNF-05: los campos del panel miden 44 px de alto, como el resto de los controles de la ventanilla.
const campo = `${inputClass} h-11`;

interface Confirmacion {
  titulo: string;
  texto: string;
  accion: () => Promise<void>;
}

interface ConfiguracionViewProps {
  onCambioHabitaciones: () => Promise<void>;
}

// RF-11 ampliado (acta del 27/10/2026): la gerencia cambia la tarifa, el fondo de cambio, los artículos, las
// habitaciones y los conserjes sin pedírselo al autor. Cada cambio rige hacia adelante (RN-DER-06) y ninguna baja
// borra historia.
const ConfiguracionView: React.FC<ConfiguracionViewProps> = ({ onCambioHabitaciones }) => {
  const { toast } = useToast();
  const [seccion, setSeccion] = useState<Seccion>('tarifa');
  const [tarifas, setTarifas] = useState<Tarifa[]>([]);
  const [fondo, setFondo] = useState<FondoCambio | null>(null);
  const [articulos, setArticulos] = useState<Articulo[]>([]);
  const [habitaciones, setHabitaciones] = useState<HabitacionConfiguracion[]>([]);
  const [operadores, setOperadores] = useState<OperadorEstado[]>([]);
  const [estado, setEstado] = useState<'cargando' | 'ok' | 'error'>('cargando');
  const [confirmacion, setConfirmacion] = useState<Confirmacion | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const [t, f, a, h, o] = await Promise.all([
        api.getTarifas(),
        api.getFondoCambio(),
        api.getArticulosConfiguracion(),
        api.getHabitacionesConfiguracion(),
        api.getOperadores(),
      ]);
      setTarifas(t);
      setFondo(f);
      setArticulos(a);
      setHabitaciones(h);
      setOperadores(o);
      setEstado('ok');
    } catch (err) {
      setEstado('error');
      toast(getErrorMessage(err, 'No se pudo cargar la configuración.'), 'error');
    }
  }, [toast]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  // Ejecuta un cambio, avisa el resultado y recarga el panel.
  const ejecutar = async (accion: () => Promise<unknown>, exito: string, error: string): Promise<boolean> => {
    setOcupado(true);
    try {
      await accion();
      toast(exito, 'success');
      await cargar();
      return true;
    } catch (err) {
      toast(getErrorMessage(err, error), 'error');
      return false;
    } finally {
      setOcupado(false);
    }
  };

  return (
    <div className="w-full animate-fade-in">
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-ink">Configuración</h1>
        <p className="mt-0.5 text-sm text-muted">
          Los cambios rigen desde ahora: los turnos, consumos y guardias ya registrados conservan sus valores.
        </p>
      </div>

      <div role="tablist" aria-label="Secciones de la configuración" className="mb-5 flex flex-wrap gap-1.5">
        {SECCIONES.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={seccion === id}
            onClick={() => setSeccion(id)}
            className={`press hit flex h-11 items-center gap-2 rounded-md border px-4 text-sm ${
              seccion === id
                ? 'border-accent bg-accent-soft font-medium text-accent'
                : 'border-line-strong bg-surface text-muted hover:text-ink'
            }`}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>

      {estado === 'cargando' && <p className="py-16 text-center text-sm text-muted">Cargando configuración…</p>}
      {estado === 'error' && (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-line bg-surface py-16">
          <p className="text-sm text-muted">No se pudo obtener la configuración.</p>
          <Button variant="secondary" onClick={() => void cargar()}>
            Reintentar
          </Button>
        </div>
      )}

      {estado === 'ok' && (
        <section className="rounded-lg border border-line bg-surface p-5">
          {seccion === 'tarifa' && <SeccionTarifa tarifas={tarifas} ocupado={ocupado} ejecutar={ejecutar} />}
          {seccion === 'fondo' && fondo && <SeccionFondo fondo={fondo} ocupado={ocupado} ejecutar={ejecutar} />}
          {seccion === 'articulos' && (
            <SeccionArticulos articulos={articulos} ocupado={ocupado} ejecutar={ejecutar} confirmar={setConfirmacion} />
          )}
          {seccion === 'habitaciones' && (
            <SeccionHabitaciones
              habitaciones={habitaciones}
              ocupado={ocupado}
              ejecutar={async (accion, exito, error) => {
                const ok = await ejecutar(accion, exito, error);
                if (ok) await onCambioHabitaciones();
                return ok;
              }}
              confirmar={setConfirmacion}
            />
          )}
          {seccion === 'conserjes' && (
            <SeccionConserjes operadores={operadores} ocupado={ocupado} ejecutar={ejecutar} confirmar={setConfirmacion} />
          )}
        </section>
      )}

      {confirmacion && (
        <Modal
          title={confirmacion.titulo}
          onClose={() => setConfirmacion(null)}
          footer={
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setConfirmacion(null)}>
                Cancelar
              </Button>
              <Button
                variant="danger"
                disabled={ocupado}
                onClick={async () => {
                  await confirmacion.accion();
                  setConfirmacion(null);
                }}
              >
                Confirmar
              </Button>
            </div>
          }
        >
          <p className="text-sm text-ink">{confirmacion.texto}</p>
        </Modal>
      )}
    </div>
  );
};

type Ejecutar = (accion: () => Promise<unknown>, exito: string, error: string) => Promise<boolean>;

const numero = (valor: string): number => Number(valor.replace(',', '.'));

// --- Tarifa ------------------------------------------------------------------------------------------------------

const SeccionTarifa: React.FC<{ tarifas: Tarifa[]; ocupado: boolean; ejecutar: Ejecutar }> = ({
  tarifas,
  ocupado,
  ejecutar,
}) => {
  const vigente = tarifas.find((t) => t.vigente);
  const [form, setForm] = useState({
    tarifa_base: String(vigente?.tarifa_base ?? ''),
    estadia_base_min: String(vigente?.estadia_base_min ?? 120),
    fraccion_min: String(vigente?.fraccion_min ?? 30),
    tarifa_fraccion: String(vigente?.tarifa_fraccion ?? ''),
  });
  const set = (clave: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [clave]: e.target.value }));

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    await ejecutar(
      () =>
        api.nuevaTarifa({
          tarifa_base: numero(form.tarifa_base),
          estadia_base_min: numero(form.estadia_base_min),
          fraccion_min: numero(form.fraccion_min),
          tarifa_fraccion: numero(form.tarifa_fraccion),
        }),
      'Tarifa nueva vigente: rige para los turnos que se abran desde ahora.',
      'No se pudo cambiar la tarifa.',
    );
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <form onSubmit={guardar} className="space-y-4">
        <h2 className="text-base font-semibold text-ink">Tarifa vigente</h2>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Precio de la estadía base ($)" htmlFor="tarifa_base">
            <input id="tarifa_base" inputMode="decimal" required className={campo} value={form.tarifa_base} onChange={set('tarifa_base')} />
          </Field>
          <Field label="Minutos que incluye" htmlFor="estadia_base_min">
            <input id="estadia_base_min" inputMode="numeric" required className={campo} value={form.estadia_base_min} onChange={set('estadia_base_min')} />
          </Field>
          <Field label="Minutos de cada fracción" htmlFor="fraccion_min">
            <input id="fraccion_min" inputMode="numeric" required className={campo} value={form.fraccion_min} onChange={set('fraccion_min')} />
          </Field>
          <Field label="Precio de cada fracción ($)" htmlFor="tarifa_fraccion">
            <input id="tarifa_fraccion" inputMode="decimal" required className={campo} value={form.tarifa_fraccion} onChange={set('tarifa_fraccion')} />
          </Field>
        </div>
        <p className="text-xs text-subtle">
          La tarifa anterior no se modifica: los turnos abiertos o cerrados con ella la conservan.
        </p>
        <Button type="submit" disabled={ocupado} className="h-11">
          Guardar tarifa nueva
        </Button>
      </form>

      <div>
        <h2 className="mb-3 text-base font-semibold text-ink">Historial</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="py-2 font-medium">Desde</th>
              <th className="py-2 text-right font-medium">Estadía base</th>
              <th className="py-2 text-right font-medium">Fracción</th>
              <th className="py-2 text-right font-medium">Estado</th>
            </tr>
          </thead>
          <tbody>
            {tarifas.map((t) => (
              <tr key={t.id} className="border-t border-line">
                <td className="py-2">{formatDateTime(t.vigente_desde)}</td>
                <td className="py-2 text-right tabular-nums">
                  {formatMoney(t.tarifa_base)} · {t.estadia_base_min} min
                </td>
                <td className="py-2 text-right tabular-nums">
                  {formatMoney(t.tarifa_fraccion)} · {t.fraccion_min} min
                </td>
                <td className={`py-2 text-right ${t.vigente ? 'font-medium text-libre' : 'text-muted'}`}>
                  {t.vigente ? 'Vigente' : 'Anterior'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// --- Fondo de cambio ---------------------------------------------------------------------------------------------

const SeccionFondo: React.FC<{ fondo: FondoCambio; ocupado: boolean; ejecutar: Ejecutar }> = ({
  fondo,
  ocupado,
  ejecutar,
}) => {
  const [monto, setMonto] = useState(String(fondo.fondo_cambio));

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    await ejecutar(
      () => api.setFondoCambio(numero(monto)),
      'Fondo de cambio actualizado: rige desde la guardia siguiente.',
      'No se pudo cambiar el fondo de cambio.',
    );
  };

  return (
    <form onSubmit={guardar} className="max-w-md space-y-4">
      <h2 className="text-base font-semibold text-ink">Fondo de cambio de cada caja</h2>
      <p className="text-sm text-muted">
        Vigente: <span className="font-medium text-ink tabular-nums">{formatMoney(fondo.fondo_cambio)}</span>
        {fondo.actualizado_en && <> · cambiado el {formatDateTime(fondo.actualizado_en)}</>}
      </p>
      <Field label="Monto nuevo ($)" htmlFor="fondo" hint="La guardia abierta conserva el fondo con el que empezó.">
        <input id="fondo" inputMode="decimal" required className={campo} value={monto} onChange={(e) => setMonto(e.target.value)} />
      </Field>
      <Button type="submit" disabled={ocupado} className="h-11">
        Guardar fondo de cambio
      </Button>
    </form>
  );
};

// --- Artículos ---------------------------------------------------------------------------------------------------

interface SeccionConBajas {
  ocupado: boolean;
  ejecutar: Ejecutar;
  confirmar: (c: Confirmacion) => void;
}

const SeccionArticulos: React.FC<SeccionConBajas & { articulos: Articulo[] }> = ({
  articulos,
  ocupado,
  ejecutar,
  confirmar,
}) => {
  const [editando, setEditando] = useState<Articulo | null>(null);
  const [form, setForm] = useState({ descripcion: '', categoria: '', precio: '', stock: '' });

  const editar = (a: Articulo) => {
    setForm({
      descripcion: a.descripcion,
      categoria: a.categoria ?? '',
      precio: String(a.precio_unitario),
      stock: String(a.stock_actual),
    });
    setEditando(a);
  };

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editando) return;
    const ok = await ejecutar(
      () =>
        api.configurarArticulo(editando.id, {
          descripcion: form.descripcion.trim(),
          categoria: form.categoria.trim() || null,
          precio_unitario: numero(form.precio),
          stock_actual: numero(form.stock),
        }),
      'Artículo actualizado. Los consumos ya registrados conservan su precio.',
      'No se pudo actualizar el artículo.',
    );
    if (ok) setEditando(null);
  };

  return (
    <>
      <h2 className="mb-1 text-base font-semibold text-ink">Artículos y precios</h2>
      <p className="mb-4 text-sm text-muted">El alta de artículos nuevos se hace desde Inventario.</p>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted">
          <tr>
            <th className="py-2 font-medium">Código</th>
            <th className="py-2 font-medium">Descripción</th>
            <th className="py-2 text-right font-medium">Precio</th>
            <th className="py-2 text-right font-medium">Stock</th>
            <th className="py-2 text-right font-medium">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {articulos.map((a) => (
            <tr key={a.id} className={`border-t border-line ${a.activo === false ? 'text-muted' : ''}`}>
              <td className="py-2 font-mono text-xs">{a.codigo}</td>
              <td className="py-2">
                {a.descripcion}
                {a.activo === false && <span className="ml-2 text-xs">(dado de baja)</span>}
              </td>
              <td className="py-2 text-right tabular-nums">{formatMoney(a.precio_unitario)}</td>
              <td className="py-2 text-right tabular-nums">{a.stock_actual}</td>
              <td className="py-2">
                <div className="flex justify-end gap-2">
                  <Button variant="secondary" className="h-11" onClick={() => editar(a)}>
                    Editar
                  </Button>
                  {a.activo === false ? (
                    <Button
                      variant="secondary"
                      className="h-11"
                      disabled={ocupado}
                      onClick={() =>
                        void ejecutar(
                          () => api.configurarArticulo(a.id, { activo: true }),
                          `${a.descripcion} vuelve a la venta.`,
                          'No se pudo reactivar el artículo.',
                        )
                      }
                    >
                      Reactivar
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      className="h-11"
                      onClick={() =>
                        confirmar({
                          titulo: 'Dar de baja el artículo',
                          texto: `${a.descripcion} deja de ofrecerse en la ventanilla. Los consumos ya registrados no cambian.`,
                          accion: async () => {
                            await ejecutar(
                              () => api.configurarArticulo(a.id, { activo: false }),
                              `${a.descripcion} dado de baja.`,
                              'No se pudo dar de baja el artículo.',
                            );
                          },
                        })
                      }
                    >
                      Dar de baja
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {editando && (
        <Modal title="Editar artículo" subtitle={editando.codigo} onClose={() => setEditando(null)}>
          <form onSubmit={guardar} className="space-y-4">
            <Field label="Descripción" htmlFor="art_desc">
              <input id="art_desc" required className={campo} value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} />
            </Field>
            <Field label="Categoría" htmlFor="art_cat">
              <input id="art_cat" className={campo} value={form.categoria} onChange={(e) => setForm({ ...form, categoria: e.target.value })} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Precio ($)" htmlFor="art_precio">
                <input id="art_precio" inputMode="decimal" required className={campo} value={form.precio} onChange={(e) => setForm({ ...form, precio: e.target.value })} />
              </Field>
              <Field label="Stock" htmlFor="art_stock">
                <input id="art_stock" inputMode="numeric" required className={campo} value={form.stock} onChange={(e) => setForm({ ...form, stock: e.target.value })} />
              </Field>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" className="h-11" onClick={() => setEditando(null)}>
                Cancelar
              </Button>
              <Button type="submit" className="h-11" disabled={ocupado}>
                Guardar
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
};

// --- Habitaciones ------------------------------------------------------------------------------------------------

const SeccionHabitaciones: React.FC<SeccionConBajas & { habitaciones: HabitacionConfiguracion[] }> = ({
  habitaciones,
  ocupado,
  ejecutar,
  confirmar,
}) => {
  const [nueva, setNueva] = useState('');
  const [renumerando, setRenumerando] = useState<HabitacionConfiguracion | null>(null);
  const [numeroNuevo, setNumeroNuevo] = useState('');

  const agregar = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await ejecutar(
      () => api.altaHabitacion(numero(nueva)),
      `${formatRoomNumber(numero(nueva))} agregada a la grilla.`,
      'No se pudo agregar la habitación.',
    );
    if (ok) setNueva('');
  };

  const renumerar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!renumerando) return;
    const ok = await ejecutar(
      () => api.configurarHabitacion(renumerando.id, { numero: numero(numeroNuevo) }),
      `La habitación ahora es la ${formatRoomNumber(numero(numeroNuevo))}.`,
      'No se pudo cambiar el número.',
    );
    if (ok) setRenumerando(null);
  };

  return (
    <>
      <form onSubmit={agregar} className="mb-5 flex flex-wrap items-end gap-3">
        <Field label="Número de la habitación nueva" htmlFor="hab_nueva">
          <input id="hab_nueva" inputMode="numeric" required className={`${campo} w-48`} value={nueva} onChange={(e) => setNueva(e.target.value)} />
        </Field>
        <Button type="submit" className="h-11" disabled={ocupado}>
          Agregar habitación
        </Button>
      </form>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted">
          <tr>
            <th className="py-2 font-medium">Habitación</th>
            <th className="py-2 font-medium">Estado</th>
            <th className="py-2 text-right font-medium">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {habitaciones.map((h) => (
            <tr key={h.id} className={`border-t border-line ${h.activa ? '' : 'text-muted'}`}>
              <td className="py-2 font-medium">{formatRoomNumber(h.numero)}</td>
              <td className="py-2">{h.activa ? h.estado : 'Dada de baja (conserva su historial)'}</td>
              <td className="py-2">
                <div className="flex justify-end gap-2">
                  <Button
                    variant="secondary"
                    className="h-11"
                    disabled={h.estado === 'Ocupada'}
                    title={h.estado === 'Ocupada' ? 'Tiene un turno en curso' : undefined}
                    onClick={() => {
                      setNumeroNuevo(String(h.numero));
                      setRenumerando(h);
                    }}
                  >
                    Cambiar número
                  </Button>
                  {h.activa ? (
                    <Button
                      variant="ghost"
                      className="h-11"
                      disabled={h.estado === 'Ocupada'}
                      title={h.estado === 'Ocupada' ? 'Tiene un turno en curso' : undefined}
                      onClick={() =>
                        confirmar({
                          titulo: 'Dar de baja la habitación',
                          texto: `${formatRoomNumber(h.numero)} sale de la grilla. Sus turnos registrados se conservan.`,
                          accion: async () => {
                            await ejecutar(
                              () => api.configurarHabitacion(h.id, { activa: false }),
                              `${formatRoomNumber(h.numero)} dada de baja.`,
                              'No se pudo dar de baja la habitación.',
                            );
                          },
                        })
                      }
                    >
                      Dar de baja
                    </Button>
                  ) : (
                    <Button
                      variant="secondary"
                      className="h-11"
                      disabled={ocupado}
                      onClick={() =>
                        void ejecutar(
                          () => api.configurarHabitacion(h.id, { activa: true }),
                          `${formatRoomNumber(h.numero)} vuelve a la grilla.`,
                          'No se pudo reactivar la habitación.',
                        )
                      }
                    >
                      Reactivar
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {renumerando && (
        <Modal title="Cambiar número" subtitle={formatRoomNumber(renumerando.numero)} onClose={() => setRenumerando(null)}>
          <form onSubmit={renumerar} className="space-y-4">
            <Field label="Número nuevo" htmlFor="hab_numero">
              <input id="hab_numero" inputMode="numeric" required className={campo} value={numeroNuevo} onChange={(e) => setNumeroNuevo(e.target.value)} />
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" className="h-11" onClick={() => setRenumerando(null)}>
                Cancelar
              </Button>
              <Button type="submit" className="h-11" disabled={ocupado}>
                Guardar
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
};

// --- Conserjes ---------------------------------------------------------------------------------------------------

const FORM_CONSERJE = { usuario: '', nombre_visible: '', clave: '' };

const SeccionConserjes: React.FC<SeccionConBajas & { operadores: OperadorEstado[] }> = ({
  operadores,
  ocupado,
  ejecutar,
  confirmar,
}) => {
  const [form, setForm] = useState(FORM_CONSERJE);

  const alta = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await ejecutar(
      () => api.altaConserje({ ...form, usuario: form.usuario.trim().toLowerCase() }),
      `Conserje ${form.usuario} dado de alta. Ya puede iniciar sesión.`,
      'No se pudo dar de alta al conserje.',
    );
    if (ok) setForm(FORM_CONSERJE);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <table className="w-full self-start text-sm">
        <thead className="text-left text-xs text-muted">
          <tr>
            <th className="py-2 font-medium">Nombre</th>
            <th className="py-2 font-medium">Usuario</th>
            <th className="py-2 font-medium">Último acceso</th>
            <th className="py-2 text-right font-medium">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {operadores.map((o) => (
            <tr key={o.id} className={`border-t border-line ${o.activo ? '' : 'text-muted'}`}>
              <td className="py-2">
                {o.nombre_visible}
                {o.rol === 'ADMINISTRADOR' && <span className="ml-2 text-xs text-muted">(gerencia)</span>}
                {!o.activo && <span className="ml-2 text-xs">(dado de baja)</span>}
              </td>
              <td className="py-2 font-mono text-xs">{o.usuario}</td>
              <td className="py-2">{o.ultimo_acceso ? formatDateTime(o.ultimo_acceso) : '—'}</td>
              <td className="py-2">
                <div className="flex justify-end">
                  {o.rol === 'OPERADOR' &&
                    (o.activo ? (
                      <Button
                        variant="ghost"
                        className="h-11"
                        onClick={() =>
                          confirmar({
                            titulo: 'Dar de baja al conserje',
                            texto: `${o.nombre_visible} ya no puede iniciar sesión. Sus guardias, arqueos y turnos se conservan a su nombre.`,
                            accion: async () => {
                              await ejecutar(
                                () => api.setOperadorActivo(o.id, false),
                                `${o.nombre_visible} dado de baja.`,
                                'No se pudo dar de baja al conserje.',
                              );
                            },
                          })
                        }
                      >
                        Dar de baja
                      </Button>
                    ) : (
                      <Button
                        variant="secondary"
                        className="h-11"
                        disabled={ocupado}
                        onClick={() =>
                          void ejecutar(
                            () => api.setOperadorActivo(o.id, true),
                            `${o.nombre_visible} puede volver a iniciar sesión.`,
                            'No se pudo reactivar al conserje.',
                          )
                        }
                      >
                        Reactivar
                      </Button>
                    ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <form onSubmit={alta} className="space-y-4 rounded-md border border-line p-4">
        <h2 className="text-base font-semibold text-ink">Alta de conserje</h2>
        <Field label="Nombre visible" htmlFor="c_nombre" hint="Solo un nombre para la pantalla: sin DNI ni otros datos.">
          <input id="c_nombre" required maxLength={60} className={campo} value={form.nombre_visible} onChange={(e) => setForm({ ...form, nombre_visible: e.target.value })} />
        </Field>
        <Field label="Usuario" htmlFor="c_usuario" hint="De 3 a 40 minúsculas, números, punto o guion.">
          <input id="c_usuario" required pattern="[a-z0-9._\-]{3,40}" className={campo} value={form.usuario} onChange={(e) => setForm({ ...form, usuario: e.target.value })} />
        </Field>
        <Field label="Clave inicial" htmlFor="c_clave" hint="Al menos 10 caracteres.">
          <input id="c_clave" type="password" required minLength={10} autoComplete="new-password" className={campo} value={form.clave} onChange={(e) => setForm({ ...form, clave: e.target.value })} />
        </Field>
        <Button type="submit" className="h-11 w-full" disabled={ocupado}>
          Dar de alta
        </Button>
      </form>
    </div>
  );
};

export default ConfiguracionView;
