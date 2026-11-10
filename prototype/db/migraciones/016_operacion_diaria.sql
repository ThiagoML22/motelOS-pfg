-- db/migraciones/016_operacion_diaria.sql
-- Demostracion del Sprint 4 (copia local, no entregada): operacion diaria.
-- Se aplica con el usuario dueno de las tablas, despues de 015_cliente_ampliado.sql.
--
-- Traslado de un turno a otra habitacion, arreglos por habitacion, recuento de toallas y sabanas en cada guardia y
-- traspaso entre guardias. Lo que documenta un hecho (traslados, recuentos, movimientos de ropa, traspasos) es de solo
-- agregado. Un arreglo se abre, se resuelve una vez y no se borra.

ALTER TABLE eventos_habitacion DROP CONSTRAINT eventos_habitacion_origen_check;
ALTER TABLE eventos_habitacion ADD CONSTRAINT eventos_habitacion_origen_check
    CHECK (origen IN ('TURNO', 'COBRO', 'LIBERAR', 'MANUAL', 'TRASLADO', 'ARREGLO'));

ALTER TABLE registro_actividad DROP CONSTRAINT registro_actividad_categoria_check;
ALTER TABLE registro_actividad ADD CONSTRAINT registro_actividad_categoria_check
    CHECK (categoria IN ('INVENTARIO', 'TARIFA', 'CAJA', 'HABITACION', 'PERSONAL', 'ESTABLECIMIENTO', 'PERFIL', 'OPERACION'));

-- Traslados --------------------------------------------------------------------------------------------------------
-- El turno sigue siendo el mismo: conserva su hora, su tarifa, su cuenta y el enlace del cliente.
CREATE TABLE traslados_turno (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    turno_id UUID NOT NULL,
    desde_habitacion_id INTEGER NOT NULL,
    hacia_habitacion_id INTEGER NOT NULL,
    motivo VARCHAR(10) NOT NULL CHECK (motivo IN ('FALLA', 'CLIENTE', 'OTRO')),
    operador_id INTEGER NOT NULL,
    guardia_id INTEGER NOT NULL,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT traslados_otra_habitacion CHECK (desde_habitacion_id <> hacia_habitacion_id),
    CONSTRAINT traslados_turno_mismo_est FOREIGN KEY (establecimiento_id, turno_id)
        REFERENCES turnos (establecimiento_id, id),
    CONSTRAINT traslados_desde_mismo_est FOREIGN KEY (establecimiento_id, desde_habitacion_id)
        REFERENCES habitaciones (establecimiento_id, id),
    CONSTRAINT traslados_hacia_mismo_est FOREIGN KEY (establecimiento_id, hacia_habitacion_id)
        REFERENCES habitaciones (establecimiento_id, id),
    CONSTRAINT traslados_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id),
    CONSTRAINT traslados_guardia_mismo_est FOREIGN KEY (establecimiento_id, guardia_id)
        REFERENCES guardias (establecimiento_id, id)
);

CREATE INDEX traslados_recientes ON traslados_turno (establecimiento_id, creado_en DESC);
CREATE INDEX traslados_del_turno ON traslados_turno (establecimiento_id, turno_id);

-- Quien registra un hecho lo hace a su nombre y en su guardia abierta; la hora la pone la base.
CREATE OR REPLACE FUNCTION check_hecho_de_guardia()
RETURNS TRIGGER AS $$
DECLARE
    g RECORD;
BEGIN
    IF current_user = 'motel_app' AND NEW.operador_id IS DISTINCT FROM app_operador() THEN
        RAISE EXCEPTION 'Operacion: se registra solo a nombre del usuario de la sesion.';
    END IF;
    SELECT estado, operador_id INTO g FROM guardias WHERE id = NEW.guardia_id;
    IF g.estado IS DISTINCT FROM 'Abierta' OR g.operador_id IS DISTINCT FROM NEW.operador_id THEN
        RAISE EXCEPTION 'Operacion: la guardia % no es la guardia abierta de quien registra.', NEW.guardia_id;
    END IF;
    NEW.creado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_traslado_turno
BEFORE INSERT ON traslados_turno
FOR EACH ROW
EXECUTE FUNCTION check_hecho_de_guardia();

-- Un turno cambia de habitacion solo con su traslado registrado en la misma transaccion.
CREATE OR REPLACE FUNCTION check_turno_trasladado()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.habitacion_id IS DISTINCT FROM OLD.habitacion_id AND NOT EXISTS (
        SELECT 1 FROM traslados_turno
         WHERE turno_id = NEW.id AND desde_habitacion_id = OLD.habitacion_id AND hacia_habitacion_id = NEW.habitacion_id
           AND creado_en = CURRENT_TIMESTAMP
    ) THEN
        RAISE EXCEPTION 'Traslados: el turno % cambia de habitacion sin un traslado registrado.', OLD.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_turno_trasladado
BEFORE UPDATE OF habitacion_id ON turnos
FOR EACH ROW
EXECUTE FUNCTION check_turno_trasladado();

-- Arreglos ---------------------------------------------------------------------------------------------------------
CREATE TABLE arreglos (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    habitacion_id INTEGER NOT NULL,
    tipo VARCHAR(15) NOT NULL CHECK (tipo IN ('FALLA', 'MANTENIMIENTO')),
    rubro VARCHAR(15) NOT NULL CHECK (rubro IN ('AIRE', 'PLOMERIA', 'ELECTRICIDAD', 'TV', 'MUEBLES', 'OTRO')),
    descripcion VARCHAR(200) NOT NULL CHECK (length(trim(descripcion)) > 0),
    estado VARCHAR(10) NOT NULL DEFAULT 'Abierto' CHECK (estado IN ('Abierto', 'En curso', 'Resuelto')),
    abierto_por_id INTEGER NOT NULL,
    abierto_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resuelto_por_id INTEGER,
    resuelto_en TIMESTAMP WITH TIME ZONE,
    -- La persona o el servicio que lo reparo, y lo que costo si se sabe. El costo es informativo: no mueve la caja.
    reparado_por VARCHAR(80),
    trabajo VARCHAR(200),
    costo NUMERIC(10, 2) CHECK (costo IS NULL OR costo >= 0),
    CONSTRAINT arreglos_resolucion_coherente CHECK (
        (estado = 'Resuelto') = (resuelto_por_id IS NOT NULL AND resuelto_en IS NOT NULL AND reparado_por IS NOT NULL)),
    CONSTRAINT arreglos_habitacion_mismo_est FOREIGN KEY (establecimiento_id, habitacion_id)
        REFERENCES habitaciones (establecimiento_id, id),
    CONSTRAINT arreglos_abre_mismo_est FOREIGN KEY (establecimiento_id, abierto_por_id)
        REFERENCES operadores (establecimiento_id, id),
    CONSTRAINT arreglos_resuelve_mismo_est FOREIGN KEY (establecimiento_id, resuelto_por_id)
        REFERENCES operadores (establecimiento_id, id)
);

CREATE INDEX arreglos_de_la_habitacion ON arreglos (establecimiento_id, habitacion_id, abierto_en DESC);
CREATE INDEX arreglos_sin_resolver ON arreglos (establecimiento_id, estado);

CREATE OR REPLACE FUNCTION check_arreglo_alta()
RETURNS TRIGGER AS $$
BEGIN
    IF current_user = 'motel_app' AND NEW.abierto_por_id IS DISTINCT FROM app_operador() THEN
        RAISE EXCEPTION 'Arreglos: se abren solo a nombre del usuario de la sesion.';
    END IF;
    IF NEW.estado <> 'Abierto' AND current_user = 'motel_app' THEN
        RAISE EXCEPTION 'Arreglos: un arreglo nuevo siempre empieza abierto.';
    END IF;
    NEW.abierto_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_arreglo_alta
BEFORE INSERT ON arreglos
FOR EACH ROW
EXECUTE FUNCTION check_arreglo_alta();

-- Lo reportado no cambia. Se resuelve una sola vez, a nombre de la sesion; despues solo se puede cargar el costo, que
-- suele llegar con la factura.
CREATE OR REPLACE FUNCTION check_arreglo_cambio()
RETURNS TRIGGER AS $$
BEGIN
    IF (NEW.establecimiento_id, NEW.habitacion_id, NEW.tipo, NEW.rubro, NEW.descripcion, NEW.abierto_por_id, NEW.abierto_en)
       IS DISTINCT FROM (OLD.establecimiento_id, OLD.habitacion_id, OLD.tipo, OLD.rubro, OLD.descripcion, OLD.abierto_por_id,
                         OLD.abierto_en) THEN
        RAISE EXCEPTION 'Arreglos: lo reportado no se modifica.';
    END IF;
    IF OLD.estado = 'Resuelto' THEN
        IF (NEW.estado, NEW.resuelto_por_id, NEW.resuelto_en, NEW.reparado_por, NEW.trabajo)
           IS DISTINCT FROM (OLD.estado, OLD.resuelto_por_id, OLD.resuelto_en, OLD.reparado_por, OLD.trabajo) THEN
            RAISE EXCEPTION 'Arreglos: el arreglo % ya se resolvio.', OLD.id;
        END IF;
    ELSIF NEW.estado = 'Resuelto' AND current_user = 'motel_app' AND NEW.resuelto_por_id IS DISTINCT FROM app_operador() THEN
        RAISE EXCEPTION 'Arreglos: se resuelven solo a nombre del usuario de la sesion.';
    ELSIF NEW.estado = 'Abierto' AND OLD.estado = 'En curso' THEN
        RAISE EXCEPTION 'Arreglos: el arreglo % no vuelve atras.', OLD.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_arreglo_cambio
BEFORE UPDATE ON arreglos
FOR EACH ROW
EXECUTE FUNCTION check_arreglo_cambio();

-- Ropa -------------------------------------------------------------------------------------------------------------
-- Se cuenta todo lo que hay en el motel, separado en limpias, sucias y puestas en habitaciones. Lo que entra o sale del
-- motel (lavanderia afuera, compra, baja) es un movimiento: asi una diferencia sin explicar es una diferencia de verdad.
CREATE TABLE ropa_conteos (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    guardia_id INTEGER NOT NULL,
    operador_id INTEGER NOT NULL,
    momento VARCHAR(10) NOT NULL CHECK (momento IN ('APERTURA', 'CIERRE')),
    prenda VARCHAR(10) NOT NULL CHECK (prenda IN ('TOALLAS', 'SABANAS')),
    limpias INTEGER NOT NULL CHECK (limpias BETWEEN 0 AND 100000),
    sucias INTEGER NOT NULL CHECK (sucias BETWEEN 0 AND 100000),
    en_habitaciones INTEGER NOT NULL CHECK (en_habitaciones BETWEEN 0 AND 100000),
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ropa_conteos_uno_por_momento UNIQUE (establecimiento_id, guardia_id, momento, prenda),
    CONSTRAINT ropa_conteos_guardia_mismo_est FOREIGN KEY (establecimiento_id, guardia_id)
        REFERENCES guardias (establecimiento_id, id),
    CONSTRAINT ropa_conteos_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id)
);

CREATE INDEX ropa_conteos_recientes ON ropa_conteos (establecimiento_id, creado_en DESC);

CREATE TABLE ropa_movimientos (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    guardia_id INTEGER NOT NULL,
    operador_id INTEGER NOT NULL,
    prenda VARCHAR(10) NOT NULL CHECK (prenda IN ('TOALLAS', 'SABANAS')),
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('LAVANDERIA_SALE', 'LAVANDERIA_VUELVE', 'COMPRA', 'BAJA')),
    cantidad INTEGER NOT NULL CHECK (cantidad BETWEEN 1 AND 100000),
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ropa_movimientos_guardia_mismo_est FOREIGN KEY (establecimiento_id, guardia_id)
        REFERENCES guardias (establecimiento_id, id),
    CONSTRAINT ropa_movimientos_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id)
);

CREATE INDEX ropa_movimientos_recientes ON ropa_movimientos (establecimiento_id, creado_en DESC);

CREATE TRIGGER trigger_ropa_conteo
BEFORE INSERT ON ropa_conteos
FOR EACH ROW
EXECUTE FUNCTION check_hecho_de_guardia();

CREATE TRIGGER trigger_ropa_movimiento
BEFORE INSERT ON ropa_movimientos
FOR EACH ROW
EXECUTE FUNCTION check_hecho_de_guardia();

-- Traspasos --------------------------------------------------------------------------------------------------------
-- Lo que quien entra recibio al abrir su guardia, como foto: no cambia aunque despues cambie la ventanilla. No lleva
-- importes ni patentes.
CREATE TABLE traspasos (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    guardia_saliente_id INTEGER,
    guardia_id INTEGER NOT NULL,
    operador_id INTEGER NOT NULL,
    resumen JSON NOT NULL,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT traspasos_uno_por_guardia UNIQUE (establecimiento_id, guardia_id),
    CONSTRAINT traspasos_saliente_mismo_est FOREIGN KEY (establecimiento_id, guardia_saliente_id)
        REFERENCES guardias (establecimiento_id, id),
    CONSTRAINT traspasos_guardia_mismo_est FOREIGN KEY (establecimiento_id, guardia_id)
        REFERENCES guardias (establecimiento_id, id),
    CONSTRAINT traspasos_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id)
);

CREATE INDEX traspasos_recientes ON traspasos (establecimiento_id, creado_en DESC);

CREATE TRIGGER trigger_traspaso
BEFORE INSERT ON traspasos
FOR EACH ROW
EXECUTE FUNCTION check_hecho_de_guardia();

-- Permisos ---------------------------------------------------------------------------------------------------------
DO $$
DECLARE
    tabla TEXT;
BEGIN
    FOREACH tabla IN ARRAY ARRAY['traslados_turno', 'arreglos', 'ropa_conteos', 'ropa_movimientos', 'traspasos'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tabla);
        EXECUTE format(
            'CREATE POLICY aislamiento_establecimiento ON %I TO motel_app '
            'USING (establecimiento_id = app_establecimiento()) '
            'WITH CHECK (establecimiento_id = app_establecimiento())', tabla);
        EXECUTE format('GRANT SELECT, INSERT ON %I TO motel_app', tabla);
        EXECUTE format('GRANT USAGE ON SEQUENCE %I TO motel_app', tabla || '_id_seq');
    END LOOP;
END $$;

GRANT UPDATE (estado, resuelto_por_id, resuelto_en, reparado_por, trabajo, costo) ON arreglos TO motel_app;
