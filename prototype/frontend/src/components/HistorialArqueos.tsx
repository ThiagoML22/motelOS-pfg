import React, { useCallback, useEffect, useState } from 'react';
import { CalendarSearch, ChevronDown, ChevronsDownUp, FileDown, FileSpreadsheet } from 'lucide-react';
import { Arqueo, ResumenMes } from '../types';
import { api, descargar, getErrorMessage } from '../services/api';
import { formatMoney, parseUtc } from '../utils/format';
import { CATEGORIA_META, formatPorcentaje } from '../utils/caja';
import Button from './ui/Button';
import { useToast } from './ui/Toast';

// Historial de arqueos segmentado (como el «Drawer History» de los sistemas de punto de venta): un mes por bloque
// desplegable con su resumen, y dentro, cada día con las guardias de mañana, tarde y noche. El día es el de la apertura
// de la guardia: la de la noche del lunes figura el lunes aunque se arquee el martes a la mañana.

const TDC_LINEA_DE_BASE = 0.1;
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
  'noviembre', 'diciembre'];
const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
const FRANJA: Record<string, string> = { '06:00': 'Mañana', '14:00': 'Tarde', '22:00': 'Noche' };

const pad = (n: number) => String(n).padStart(2, '0');
const claveDia = (fecha: Date) => `${fecha.getFullYear()}-${pad(fecha.getMonth() + 1)}-${pad(fecha.getDate())}`;
const nombreMes = (mes: string) => {
  const [anio, numero] = mes.split('-').map(Number);
  const nombre = MESES[numero - 1];
  return `${nombre[0].toUpperCase()}${nombre.slice(1)} ${anio}`;
};
const sumarDias = (iso: string, dias: number) => {
  const fecha = new Date(`${iso}T12:00:00`);
  fecha.setDate(fecha.getDate() + dias);
  return claveDia(fecha);
};

interface HistorialArqueosProps {
  operadorId: number | '';
  // Cambia cuando el panel se recarga (por ejemplo, después de un cierre supervisado).
  version: number;
  onAbrir: (arqueoId: number) => void;
}

type Carga = Arqueo[] | 'cargando' | 'error';

const HistorialArqueos: React.FC<HistorialArqueosProps> = ({ operadorId, version, onAbrir }) => {
  const { toast } = useToast();
  const [meses, setMeses] = useState<ResumenMes[] | null>(null);
  const [abiertos, setAbiertos] = useState<Set<string>>(new Set());
  const [porMes, setPorMes] = useState<Record<string, Carga>>({});
  const [fecha, setFecha] = useState('');
  const [resaltado, setResaltado] = useState<string | null>(null);

  const operador = operadorId === '' ? undefined : operadorId;

  useEffect(() => {
    let vigente = true;
    setPorMes({});
    api
      .getArqueosMeses(operador)
      .then((lista) => {
        if (!vigente) return;
        setMeses(lista);
        setAbiertos(new Set(lista.slice(0, 1).map((m) => m.mes)));
      })
      .catch((err) => toast(getErrorMessage(err, 'No se pudo cargar el historial de arqueos.'), 'error'));
    return () => {
      vigente = false;
    };
  }, [operador, version, toast]);

  // Cada mes trae sus arqueos al abrirse por primera vez. Se pide un día de margen a cada lado (la consulta va por la
  // hora de confirmación) y se queda con las guardias abiertas dentro del mes.
  const cargarMes = useCallback(
    async (mes: ResumenMes) => {
      setPorMes((previo) => ({ ...previo, [mes.mes]: 'cargando' }));
      try {
        const lista = await api.getArqueos({
          desde: sumarDias(mes.desde, -1),
          hasta: sumarDias(mes.hasta, 1),
          operador_id: operador,
        });
        const propios = lista.filter((a) => claveDia(parseUtc(a.abierta_en)).startsWith(mes.mes));
        setPorMes((previo) => ({ ...previo, [mes.mes]: propios }));
      } catch {
        setPorMes((previo) => ({ ...previo, [mes.mes]: 'error' }));
      }
    },
    [operador],
  );

  useEffect(() => {
    meses?.filter((m) => abiertos.has(m.mes) && !porMes[m.mes]).forEach((m) => void cargarMes(m));
  }, [meses, abiertos, porMes, cargarMes]);

  // Después de «Ir a una fecha», cuando el día aparece en pantalla, se lo lleva a la vista y se lo resalta un momento.
  useEffect(() => {
    if (!resaltado) return;
    const elemento = document.getElementById(`dia-${resaltado}`);
    if (!elemento) return;
    elemento.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const fin = setTimeout(() => setResaltado(null), 2500);
    return () => clearTimeout(fin);
  }, [resaltado, porMes]);

  // Exportación del mes: el PDF lo arma el servidor; el CSV (separador «;» y BOM para que Excel respete las tildes),
  // el navegador con los arqueos del mes.
  const exportarPdf = async (mes: ResumenMes) => {
    try {
      await api.descargarInformeMes(mes.mes, operador);
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo generar el informe en PDF.'), 'error');
    }
  };

  const exportarCsv = async (mes: ResumenMes) => {
    try {
      const cargados = porMes[mes.mes];
      const lista = Array.isArray(cargados)
        ? cargados
        : (
            await api.getArqueos({ desde: sumarDias(mes.desde, -1), hasta: sumarDias(mes.hasta, 1), operador_id: operador })
          ).filter((a) => claveDia(parseUtc(a.abierta_en)).startsWith(mes.mes));
      const celda = (valor: unknown) => `"${String(valor ?? '').replace(/"/g, '""')}"`;
      const numero = (valor: number) => String(valor).replace('.', ',');
      const filas = [
        ['Día', 'Guardia', 'Conserje', 'Fondo inicial', 'Declarado', 'Sistema', 'Diferencia', 'Resultado', 'Supervisado', 'Observación'],
        ...[...lista]
          .sort((x, y) => parseUtc(x.abierta_en).getTime() - parseUtc(y.abierta_en).getTime())
          .map((a) => [
            claveDia(parseUtc(a.abierta_en)),
            FRANJA[a.franja] ?? a.franja,
            a.operador_nombre,
            numero(a.fondo_inicial),
            numero(a.total_declarado),
            numero(a.total_sistema),
            numero(a.diferencia),
            a.categoria,
            a.supervisado ? 'Sí' : 'No',
            a.observacion ?? '',
          ]),
      ];
      const texto = '﻿' + filas.map((f) => f.map(celda).join(';')).join('\r\n');
      descargar(new Blob([texto], { type: 'text/csv;charset=utf-8' }), `arqueos-${mes.mes}.csv`);
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo exportar el mes.'), 'error');
    }
  };

  const alternar = (mes: string) =>
    setAbiertos((previo) => {
      const nuevo = new Set(previo);
      if (nuevo.has(mes)) nuevo.delete(mes);
      else nuevo.add(mes);
      return nuevo;
    });

  const irAFecha = (valor: string) => {
    setFecha(valor);
    if (!valor) return;
    const mes = valor.slice(0, 7);
    if (!meses?.some((m) => m.mes === mes)) {
      toast('No hay arqueos en ese mes.', 'error');
      return;
    }
    setAbiertos((previo) => new Set(previo).add(mes));
    setResaltado(valor);
  };

  return (
    <section aria-labelledby="titulo-arqueos">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="titulo-arqueos" className="text-sm font-semibold text-ink">
            Historial de arqueos
          </h2>
          <p className="text-xs text-muted">Por mes y por día; tocá una guardia para ver sus cobros y el comprobante.</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="flex flex-col gap-1 text-xs font-medium text-muted">
            <span className="flex items-center gap-1">
              <CalendarSearch className="h-3.5 w-3.5" aria-hidden="true" />
              Ir a una fecha
            </span>
            <input
              type="date"
              value={fecha}
              onChange={(e) => irAFecha(e.target.value)}
              className="h-9 rounded-md border border-line-strong bg-surface px-2 text-sm text-ink focus:border-accent focus-visible:outline-none"
            />
          </label>
          {abiertos.size > 1 && (
            <Button variant="ghost" size="sm" className="h-9" onClick={() => setAbiertos(new Set())}>
              <ChevronsDownUp className="h-3.5 w-3.5" aria-hidden="true" />
              Contraer todo
            </Button>
          )}
        </div>
      </div>

      {meses === null && <p className="py-8 text-center text-sm text-muted">Cargando historial…</p>}
      {meses?.length === 0 && (
        <p className="rounded-lg border border-line bg-surface py-10 text-center text-sm text-muted">Todavía no hay arqueos.</p>
      )}

      <div className="space-y-2">
        {meses?.map((mes) => {
          const abierto = abiertos.has(mes.mes);
          const carga = porMes[mes.mes];
          return (
            <div key={mes.mes} className="overflow-hidden rounded-lg border border-line bg-surface">
              <div className="flex items-center gap-2 pr-3 hover:bg-surface-2">
              <button
                type="button"
                onClick={() => alternar(mes.mes)}
                aria-expanded={abierto}
                className="flex min-w-0 flex-1 flex-wrap items-center gap-x-6 gap-y-1 px-4 py-3 text-left"
              >
                <span className="flex min-w-[11rem] items-center gap-2 font-semibold text-ink">
                  <ChevronDown className={`h-4 w-4 text-muted transition-transform ${abierto ? '' : '-rotate-90'}`} aria-hidden="true" />
                  {nombreMes(mes.mes)}
                </span>
                <Dato etiqueta="Arqueos" valor={String(mes.arqueos)} />
                <Dato
                  etiqueta="TDC"
                  valor={formatPorcentaje(mes.tdc)}
                  clase={mes.tdc > TDC_LINEA_DE_BASE ? 'text-danger' : 'text-ink'}
                />
                <Dato etiqueta="Faltantes" valor={`${mes.faltantes} · ${formatMoney(mes.total_faltante)}`} clase="text-danger" />
                <Dato etiqueta="Sobrantes" valor={`${mes.sobrantes} · ${formatMoney(mes.total_sobrante)}`} clase="text-warn" />
              </button>
              <div className="flex shrink-0 gap-1" role="group" aria-label={`Exportar ${nombreMes(mes.mes)}`}>
                <Button variant="ghost" size="sm" title="Informe del mes en PDF" onClick={() => void exportarPdf(mes)}>
                  <FileDown className="h-3.5 w-3.5" aria-hidden="true" />
                  PDF
                </Button>
                <Button variant="ghost" size="sm" title="Arqueos del mes para Excel (CSV)" onClick={() => void exportarCsv(mes)}>
                  <FileSpreadsheet className="h-3.5 w-3.5" aria-hidden="true" />
                  Excel
                </Button>
              </div>
              </div>
              {abierto && (
                <div className="border-t border-line">
                  {carga === 'cargando' || carga === undefined ? (
                    <p className="px-4 py-6 text-center text-sm text-muted">Cargando {nombreMes(mes.mes).toLowerCase()}…</p>
                  ) : carga === 'error' ? (
                    <p className="px-4 py-6 text-center text-sm text-danger">No se pudieron cargar los arqueos del mes.</p>
                  ) : (
                    <DiasDelMes arqueos={carga} resaltado={resaltado} onAbrir={onAbrir} />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
};

const Dato: React.FC<{ etiqueta: string; valor: string; clase?: string }> = ({ etiqueta, valor, clase = 'text-ink' }) => (
  <span className="text-xs text-muted">
    {etiqueta} <span className={`ml-1 text-sm font-medium tabular-nums ${clase}`}>{valor}</span>
  </span>
);

const DiasDelMes: React.FC<{ arqueos: Arqueo[]; resaltado: string | null; onAbrir: (id: number) => void }> = ({
  arqueos,
  resaltado,
  onAbrir,
}) => {
  const porDia = new Map<string, Arqueo[]>();
  for (const a of [...arqueos].sort((x, y) => parseUtc(y.abierta_en).getTime() - parseUtc(x.abierta_en).getTime())) {
    const clave = claveDia(parseUtc(a.abierta_en));
    porDia.set(clave, [...(porDia.get(clave) ?? []), a]);
  }
  if (porDia.size === 0) return <p className="px-4 py-6 text-center text-sm text-muted">Sin arqueos en este mes.</p>;
  return (
    <ul className="divide-y divide-line">
      {[...porDia.entries()].map(([dia, lista]) => {
        const fecha = new Date(`${dia}T12:00:00`);
        const conDiferencia = lista.filter((a) => a.categoria !== 'Correcto').length;
        const guardias = [...lista].sort((x, y) => parseUtc(x.abierta_en).getTime() - parseUtc(y.abierta_en).getTime());
        return (
          <li
            key={dia}
            id={`dia-${dia}`}
            className={`grid gap-2 px-4 py-3 transition-colors md:grid-cols-[10rem_1fr] ${resaltado === dia ? 'bg-accent-soft' : ''}`}
          >
            <div>
              <p className="text-sm font-medium capitalize text-ink">
                {DIAS[fecha.getDay()]} {fecha.getDate()}/{fecha.getMonth() + 1}
              </p>
              <p className="text-xs text-muted">
                {lista.length} {lista.length === 1 ? 'guardia' : 'guardias'}
                {conDiferencia > 0 && <span className="text-danger"> · {conDiferencia} con diferencia</span>}
              </p>
            </div>
            <div className="grid gap-1.5 sm:grid-cols-3">
              {guardias.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => onAbrir(a.id)}
                  className="press flex flex-col rounded-md border border-line px-3 py-2 text-left hover:border-line-strong hover:bg-surface-2"
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-muted">{FRANJA[a.franja] ?? a.franja}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${CATEGORIA_META[a.categoria].clase}`}>
                      {a.categoria}
                    </span>
                  </span>
                  <span className="mt-1 truncate text-sm font-medium text-ink">{a.operador_nombre}</span>
                  <span className="text-xs tabular-nums text-muted">
                    Declarado {formatMoney(a.total_declarado)}
                    {a.diferencia !== 0 && (
                      <span className={a.diferencia < 0 ? 'text-danger' : 'text-warn'}> · {formatMoney(a.diferencia)}</span>
                    )}
                    {a.supervisado && <span> · supervisado</span>}
                  </span>
                </button>
              ))}
            </div>
          </li>
        );
      })}
    </ul>
  );
};

export default HistorialArqueos;
