import React, { useCallback, useEffect, useState } from 'react';
import { BedDouble, Building2, Coins, KeyRound, Package, Palette, Tags, Users, Volume2 } from 'lucide-react';
import { COLORES_SUGERIDOS, aplicarMarca, sonarAviso } from '../utils/marca';
import { Articulo, Categoria, Establecimiento, FondoCambio, HabitacionConfiguracion, OperadorEstado } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime, formatMoney, formatRoomNumber } from '../utils/format';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';
import { EsqueletoTabla } from './ui/Carga';
import SeccionCategorias, { ChipCategoria } from './CategoriasConfig';

type Seccion = 'tarifa' | 'fondo' | 'articulos' | 'habitaciones' | 'conserjes' | 'establecimiento' | 'apariencia';

const SECCIONES: { id: Seccion; label: string; icon: React.ElementType }[] = [
  { id: 'tarifa', label: 'Categorías y tarifas', icon: Tags },
  { id: 'fondo', label: 'Fondo de cambio', icon: Coins },
  { id: 'articulos', label: 'Artículos', icon: Package },
  { id: 'habitaciones', label: 'Habitaciones', icon: BedDouble },
  { id: 'conserjes', label: 'Conserjes', icon: Users },
  { id: 'establecimiento', label: 'Establecimiento', icon: Building2 },
  { id: 'apariencia', label: 'Apariencia y avisos', icon: Palette },
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
  // La apariencia viaja en la sesión: al guardarla se refresca para aplicarla en toda la interfaz.
  onCambioApariencia: () => Promise<void>;
}

// RF-11 ampliado (acta del 27/10/2026): la gerencia cambia la tarifa, el fondo de cambio, los artículos, las
// habitaciones y los conserjes sin pedírselo al autor. Cada cambio rige hacia adelante (RN-DER-06) y ninguna baja
// borra historia.
const ConfiguracionView: React.FC<ConfiguracionViewProps> = ({ onCambioHabitaciones, onCambioApariencia }) => {
  const { toast } = useToast();
  const [seccion, setSeccion] = useState<Seccion>('tarifa');
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [fondo, setFondo] = useState<FondoCambio | null>(null);
  const [articulos, setArticulos] = useState<Articulo[]>([]);
  const [habitaciones, setHabitaciones] = useState<HabitacionConfiguracion[]>([]);
  const [operadores, setOperadores] = useState<OperadorEstado[]>([]);
  const [establecimiento, setEstablecimiento] = useState<Establecimiento | null>(null);
  const [estado, setEstado] = useState<'cargando' | 'ok' | 'error'>('cargando');
  const [confirmacion, setConfirmacion] = useState<Confirmacion | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const [t, f, a, h, o, e] = await Promise.all([
        api.getCategoriasConfiguracion(),
        api.getFondoCambio(),
        api.getArticulosConfiguracion(),
        api.getHabitacionesConfiguracion(),
        api.getOperadores(),
        api.getEstablecimiento(),
      ]);
      setCategorias(t);
      setFondo(f);
      setArticulos(a);
      setHabitaciones(h);
      setOperadores(o);
      setEstablecimiento(e);
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

      {estado === 'cargando' && <EsqueletoTabla etiqueta="Cargando configuración…" />}
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
          {seccion === 'tarifa' && (
            <SeccionCategorias
              categorias={categorias}
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
          {seccion === 'fondo' && fondo && <SeccionFondo fondo={fondo} ocupado={ocupado} ejecutar={ejecutar} />}
          {seccion === 'articulos' && (
            <SeccionArticulos articulos={articulos} ocupado={ocupado} ejecutar={ejecutar} confirmar={setConfirmacion} />
          )}
          {seccion === 'habitaciones' && (
            <SeccionHabitaciones
              habitaciones={habitaciones}
              categorias={categorias}
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
          {seccion === 'establecimiento' && establecimiento && (
            <SeccionEstablecimiento key={establecimiento.nombre} establecimiento={establecimiento} ocupado={ocupado} ejecutar={ejecutar} />
          )}
          {seccion === 'apariencia' && establecimiento && (
            <SeccionApariencia
              establecimiento={establecimiento}
              ocupado={ocupado}
              ejecutar={async (accion, exito, error) => {
                const ok = await ejecutar(accion, exito, error);
                if (ok) await onCambioApariencia();
                return ok;
              }}
            />
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

// --- Apariencia y avisos (migración 009) --------------------------------------------------------------------------

const SeccionApariencia: React.FC<{ establecimiento: Establecimiento; ocupado: boolean; ejecutar: Ejecutar }> = ({
  establecimiento,
  ocupado,
  ejecutar,
}) => {
  const [color, setColor] = useState(establecimiento.color_marca ?? '');
  const [eslogan, setEslogan] = useState(establecimiento.eslogan ?? '');
  const [aviso, setAviso] = useState(String(establecimiento.aviso_por_vencer_min ?? 10));
  const [sonido, setSonido] = useState(Boolean(establecimiento.alertas_sonoras));
  const colorValido = color === '' || /^#[0-9a-fA-F]{6}$/.test(color);
  const avisoValido = /^\d{1,3}$/.test(aviso) && Number(aviso) <= 120;

  // Vista previa en vivo: el color elegido se aplica a toda la interfaz mientras se edita; al salir sin guardar
  // vuelve el de la sesión.
  const guardado = establecimiento.color_marca ?? null;
  useEffect(() => {
    if (colorValido) aplicarMarca(color || null);
  }, [color, colorValido]);
  useEffect(() => () => aplicarMarca(guardado), [guardado]);

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    await ejecutar(
      () =>
        api.setEstablecimiento({
          color_marca: color,
          eslogan,
          aviso_por_vencer_min: Number(aviso),
          alertas_sonoras: sonido,
        }),
      'Apariencia y avisos guardados: rigen en todos los puestos desde su próxima actualización.',
      'No se pudieron guardar la apariencia y los avisos.',
    );
  };

  return (
    <form onSubmit={guardar} className="grid gap-8 lg:grid-cols-2">
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-ink">Color de marca</h2>
        <p className="text-sm text-muted">
          Reemplaza el azul de MotelOS en botones, enlaces y la pantalla de ingreso. Se ajusta solo para leerse bien en
          modo claro y oscuro.
        </p>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Colores sugeridos">
          {COLORES_SUGERIDOS.map((c) => {
            const elegido = (color || '#244473').toLowerCase() === c.hex;
            return (
              <button
                key={c.hex}
                type="button"
                role="radio"
                aria-checked={elegido}
                title={c.nombre}
                onClick={() => setColor(c.hex === '#244473' ? '' : c.hex)}
                className={`press hit h-9 w-9 rounded-full border-2 ${elegido ? 'border-ink' : 'border-transparent'}`}
                style={{ backgroundColor: c.hex }}
              >
                <span className="sr-only">{c.nombre}</span>
              </button>
            );
          })}
        </div>
        <div className="flex items-end gap-3">
          <Field label="Otro color (hex)" htmlFor="ap_color" error={colorValido ? undefined : 'Formato #rrggbb'}>
            <input
              id="ap_color"
              maxLength={7}
              placeholder="#244473"
              className={`${campo} w-36 font-mono`}
              value={color}
              onChange={(e) => setColor(e.target.value.trim())}
            />
          </Field>
          <input
            type="color"
            aria-label="Elegir color"
            value={colorValido && color ? color : '#244473'}
            onChange={(e) => setColor(e.target.value)}
            className="h-11 w-14 cursor-pointer rounded-md border border-line-strong bg-surface p-1"
          />
        </div>
        <div className="rounded-md border border-line bg-surface-2 p-4">
          <p className="mb-3 text-xs font-medium uppercase tracking-wide text-subtle">Vista previa</p>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button">Botón principal</Button>
            <span className="rounded-md border border-accent bg-accent-soft px-3 py-1.5 text-sm font-medium text-accent">
              Filtro elegido
            </span>
            <span className="text-sm font-medium text-accent underline">Un enlace</span>
          </div>
        </div>
        <Field label="Eslogan" htmlFor="ap_eslogan" hint="Se ve en la pantalla de ingreso, debajo del nombre del motel.">
          <input id="ap_eslogan" maxLength={120} className={campo} value={eslogan} onChange={(e) => setEslogan(e.target.value)} />
        </Field>
      </div>

      <div className="space-y-4">
        <h2 className="text-base font-semibold text-ink">Avisos de la ventanilla</h2>
        <Field
          label="Aviso «por vencer» (minutos antes del fin del turno)"
          htmlFor="ap_aviso"
          hint="La tarjeta de la habitación se pone amarilla. 0 = sin aviso."
          error={avisoValido ? undefined : 'Entre 0 y 120 minutos'}
        >
          <input id="ap_aviso" inputMode="numeric" className={`${campo} w-32`} value={aviso} onChange={(e) => setAviso(e.target.value)} />
        </Field>
        <label className="flex cursor-pointer items-start gap-3 rounded-md border border-line p-3">
          <input type="checkbox" className="mt-1 h-4 w-4 accent-[rgb(var(--accent))]" checked={sonido} onChange={(e) => setSonido(e.target.checked)} />
          <span>
            <span className="block text-sm font-medium text-ink">Alertas sonoras</span>
            <span className="block text-sm text-muted">
              Un sonido corto en la ventanilla del conserje cuando un turno pasa a «por vencer» y otro, más agudo, cuando
              se excede.
            </span>
          </span>
        </label>
        <div className="flex gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={() => sonarAviso('por_vencer')}>
            <Volume2 className="h-3.5 w-3.5" aria-hidden="true" />
            Probar «por vencer»
          </Button>
          <Button type="button" variant="secondary" size="sm" onClick={() => sonarAviso('excedido')}>
            <Volume2 className="h-3.5 w-3.5" aria-hidden="true" />
            Probar «excedido»
          </Button>
        </div>
        <Button type="submit" disabled={ocupado || !colorValido || !avisoValido} className="h-11">
          Guardar apariencia y avisos
        </Button>
      </div>
    </form>
  );
};

// --- Establecimiento (multiinquilino) ------------------------------------------------------------------------------

const SeccionEstablecimiento: React.FC<{ establecimiento: Establecimiento; ocupado: boolean; ejecutar: Ejecutar }> = ({
  establecimiento,
  ocupado,
  ejecutar,
}) => {
  const [form, setForm] = useState({
    nombre: establecimiento.nombre,
    domicilio: establecimiento.domicilio ?? '',
    telefono: establecimiento.telefono ?? '',
    leyenda_comprobante: establecimiento.leyenda_comprobante ?? '',
    wifi_nombre: establecimiento.wifi_nombre ?? '',
    wifi_clave: establecimiento.wifi_clave ?? '',
    bienvenida: establecimiento.bienvenida ?? '',
  });
  const set = (clave: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((prev) => ({ ...prev, [clave]: e.target.value }));

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    await ejecutar(
      () => api.setEstablecimiento(form),
      'Datos del establecimiento guardados: el próximo comprobante ya los usa.',
      'No se pudieron guardar los datos del establecimiento.',
    );
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <form onSubmit={guardar} className="space-y-4">
        <h2 className="text-base font-semibold text-ink">Datos del establecimiento</h2>
        <Field label="Nombre" htmlFor="est_nombre">
          <input id="est_nombre" required maxLength={80} className={campo} value={form.nombre} onChange={set('nombre')} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Domicilio" htmlFor="est_domicilio">
            <input id="est_domicilio" maxLength={120} className={campo} value={form.domicilio} onChange={set('domicilio')} />
          </Field>
          <Field label="Teléfono" htmlFor="est_telefono">
            <input id="est_telefono" maxLength={40} className={campo} value={form.telefono} onChange={set('telefono')} />
          </Field>
        </div>
        <Field
          label="Leyenda del comprobante de arqueo"
          htmlFor="est_leyenda"
          hint="Aparece al pie del PDF que se imprime y firma en cada cierre de caja (RF-10)."
        >
          <textarea
            id="est_leyenda"
            rows={3}
            maxLength={200}
            className={inputClass}
            value={form.leyenda_comprobante}
            onChange={set('leyenda_comprobante')}
          />
        </Field>
        <h3 className="pt-2 text-sm font-semibold text-ink">Para el cliente</h3>
        <p className="-mt-3 text-xs text-muted">Lo ve en su celular, con el QR del ticket, mientras dura su estadía.</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Red de Wi-Fi" htmlFor="est_wifi">
            <input id="est_wifi" maxLength={60} className={campo} value={form.wifi_nombre} onChange={set('wifi_nombre')} />
          </Field>
          <Field label="Clave de Wi-Fi" htmlFor="est_wifi_clave">
            <input id="est_wifi_clave" maxLength={60} autoComplete="off" className={campo} value={form.wifi_clave} onChange={set('wifi_clave')} />
          </Field>
        </div>
        <Field label="Mensaje de bienvenida" htmlFor="est_bienvenida" hint="Lo dice Mot cuando el cliente entra a hablar con él.">
          <input id="est_bienvenida" maxLength={200} className={campo} value={form.bienvenida} onChange={set('bienvenida')} />
        </Field>
        <Button type="submit" disabled={ocupado || !form.nombre.trim()} className="h-11">
          Guardar datos
        </Button>
      </form>

      <dl className="space-y-3 rounded-md border border-line bg-surface-2 p-4 text-sm">
        <div>
          <dt className="text-xs text-muted">Código de ingreso</dt>
          <dd className="font-mono text-base font-medium text-ink">{establecimiento.codigo}</dd>
          <dd className="mt-1 text-xs text-subtle">
            Lo escriben los conserjes al ingresar. No cambia: lo asigna la plataforma.
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">En el sistema desde</dt>
          <dd className="text-ink">{formatDateTime(establecimiento.creado_en)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Aislamiento</dt>
          <dd className="text-ink">
            Los datos de este motel solo los ven sus usuarios: la base lo garantiza con Row Level Security.
          </dd>
        </div>
      </dl>
    </div>
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

const SeccionHabitaciones: React.FC<
  SeccionConBajas & { habitaciones: HabitacionConfiguracion[]; categorias: Categoria[] }
> = ({
  habitaciones,
  categorias,
  ocupado,
  ejecutar,
  confirmar,
}) => {
  const [nueva, setNueva] = useState('');
  const activas = categorias.filter((c) => c.activa);
  const [categoriaNueva, setCategoriaNueva] = useState<number | ''>(activas[0]?.id ?? '');
  const categoriaDe = (id: number) => categorias.find((c) => c.id === id);
  const [renumerando, setRenumerando] = useState<HabitacionConfiguracion | null>(null);
  const [numeroNuevo, setNumeroNuevo] = useState('');

  const agregar = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await ejecutar(
      () => api.altaHabitacion(numero(nueva), categoriaNueva === '' ? undefined : categoriaNueva),
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
        <Field label="Categoría" htmlFor="hab_nueva_categoria">
          <select
            id="hab_nueva_categoria"
            className={`${campo} w-56`}
            value={categoriaNueva}
            onChange={(e) => setCategoriaNueva(Number(e.target.value))}
          >
            {activas.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre}
              </option>
            ))}
          </select>
        </Field>
        <Button type="submit" className="h-11" disabled={ocupado}>
          Agregar habitación
        </Button>
      </form>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted">
          <tr>
            <th className="py-2 font-medium">Habitación</th>
            <th className="py-2 font-medium">Categoría</th>
            <th className="py-2 font-medium">Estado</th>
            <th className="py-2 text-right font-medium">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {habitaciones.map((h) => (
            <tr key={h.id} className={`border-t border-line ${h.activa ? '' : 'text-muted'}`}>
              <td className="py-2 font-medium">{formatRoomNumber(h.numero)}</td>
              <td className="py-2">
                <div className="flex items-center gap-2">
                  <ChipCategoria categoria={categoriaDe(h.categoria_id)} className="hidden sm:inline-flex" />
                  {h.activa && (
                    <select
                      aria-label={`Categoría de la ${formatRoomNumber(h.numero)}`}
                      className={`${campo} w-40`}
                      value={h.categoria_id}
                      disabled={ocupado}
                      onChange={(e) => {
                        const nueva = categoriaDe(Number(e.target.value));
                        void ejecutar(
                          () => api.configurarHabitacion(h.id, { categoria_id: Number(e.target.value) }),
                          `${formatRoomNumber(h.numero)} pasa a ${nueva?.nombre ?? 'otra categoría'}` +
                            (h.estado === 'Ocupada' ? ': el turno en curso conserva su tarifa.' : '.'),
                          'No se pudo cambiar la categoría.',
                        );
                      }}
                    >
                      {categorias
                        .filter((c) => c.activa || c.id === h.categoria_id)
                        .map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.nombre}
                          </option>
                        ))}
                    </select>
                  )}
                </div>
              </td>
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
  const [restableciendo, setRestableciendo] = useState<OperadorEstado | null>(null);
  const [claveNueva, setClaveNueva] = useState('');

  const restablecer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!restableciendo) return;
    const ok = await ejecutar(
      () => api.restablecerClave(restableciendo.id, claveNueva),
      `Clave de ${restableciendo.nombre_visible} restablecida. Comuníquesela en persona.`,
      'No se pudo restablecer la clave.',
    );
    if (ok) setRestableciendo(null);
  };

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
                <div className="flex justify-end gap-2">
                  {o.rol === 'OPERADOR' && o.activo && (
                    <Button
                      variant="secondary"
                      className="h-11"
                      aria-label={`Restablecer la clave de ${o.nombre_visible}`}
                      title="Restablecer clave"
                      onClick={() => {
                        setClaveNueva('');
                        setRestableciendo(o);
                      }}
                    >
                      <KeyRound className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  )}
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

      {restableciendo && (
        <Modal
          title="Restablecer la clave"
          subtitle={`${restableciendo.nombre_visible} (${restableciendo.usuario})`}
          onClose={() => setRestableciendo(null)}
        >
          <form onSubmit={restablecer} className="space-y-4">
            <p className="text-sm text-muted">
              La clave anterior deja de servir y se quita el bloqueo por intentos fallidos. Queda en el registro de
              actividad; la gerencia nunca ve la clave anterior.
            </p>
            <Field label="Clave nueva" htmlFor="clave_restablecida" hint="Al menos 10 caracteres.">
              <input
                id="clave_restablecida"
                data-autofocus
                type="password"
                required
                minLength={10}
                autoComplete="new-password"
                className={campo}
                value={claveNueva}
                onChange={(e) => setClaveNueva(e.target.value)}
              />
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" className="h-11" onClick={() => setRestableciendo(null)}>
                Cancelar
              </Button>
              <Button type="submit" className="h-11" disabled={ocupado || claveNueva.length < 10}>
                Restablecer
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};

export default ConfiguracionView;
