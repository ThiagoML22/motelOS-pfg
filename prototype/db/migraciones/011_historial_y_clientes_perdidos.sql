-- db/migraciones/011_historial_y_clientes_perdidos.sql
-- Demostracion del Sprint 4 (copia local, no entregada): historial de estados de las habitaciones y clientes perdidos.
-- Se aplica con el usuario dueno de las tablas, despues de 010_pedidos_reposicion.sql.
--
-- Hasta aca cada habitacion guardaba solo su estado actual: no se podia saber cuanto tarda una limpieza ni ver una
-- limpieza que no vino de un turno. Y el cliente que se iba porque no habia lugar no quedaba en ninguna parte, asi que
-- el analisis solo veia la demanda atendida. Las dos tablas son de solo agregado.

CREATE TABLE eventos_habitacion (
    id BIGSERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    habitacion_id INTEGER NOT NULL,
    estado_anterior VARCHAR(20) NOT NULL,
    estado_nuevo VARCHAR(20) NOT NULL,
    origen VARCHAR(10) NOT NULL CHECK (origen IN ('TURNO', 'COBRO', 'LIBERAR', 'MANUAL')),
    turno_id UUID,
    operador_id INTEGER NOT NULL,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT eventos_cambia_el_estado CHECK (estado_anterior <> estado_nuevo),
    CONSTRAINT eventos_habitacion_mismo_est FOREIGN KEY (establecimiento_id, habitacion_id)
        REFERENCES habitaciones (establecimiento_id, id),
    CONSTRAINT eventos_turno_mismo_est FOREIGN KEY (establecimiento_id, turno_id)
        REFERENCES turnos (establecimiento_id, id),
    CONSTRAINT eventos_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id)
);

CREATE INDEX eventos_por_habitacion ON eventos_habitacion (establecimiento_id, habitacion_id, creado_en DESC);
CREATE INDEX eventos_recientes ON eventos_habitacion (establecimiento_id, creado_en DESC);

-- El cliente que se fue sin quedarse. Lo registra el conserje en su guardia; la categoria que buscaba es opcional.
CREATE TABLE clientes_perdidos (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    motivo VARCHAR(10) NOT NULL CHECK (motivo IN ('SIN_LUGAR', 'ESPERA', 'PRECIO')),
    categoria_id INTEGER,
    operador_id INTEGER NOT NULL,
    guardia_id INTEGER NOT NULL,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT perdidos_categoria_mismo_est FOREIGN KEY (establecimiento_id, categoria_id)
        REFERENCES categorias_habitacion (establecimiento_id, id),
    CONSTRAINT perdidos_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id),
    CONSTRAINT perdidos_guardia_mismo_est FOREIGN KEY (establecimiento_id, guardia_id)
        REFERENCES guardias (establecimiento_id, id)
);

CREATE INDEX perdidos_recientes ON clientes_perdidos (establecimiento_id, creado_en DESC);

-- Un evento queda a nombre del usuario de la sesion y con la hora de la base, no la que mande la aplicacion.
CREATE OR REPLACE FUNCTION check_evento_habitacion()
RETURNS TRIGGER AS $$
BEGIN
    IF current_user = 'motel_app' AND NEW.operador_id IS DISTINCT FROM app_operador() THEN
        RAISE EXCEPTION 'Historial: los eventos se escriben solo a nombre del usuario de la sesion.';
    END IF;
    NEW.creado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_evento_habitacion
BEFORE INSERT ON eventos_habitacion
FOR EACH ROW
EXECUTE FUNCTION check_evento_habitacion();

-- Un cliente perdido se registra a nombre de quien atiende y en su guardia abierta.
CREATE OR REPLACE FUNCTION check_cliente_perdido()
RETURNS TRIGGER AS $$
DECLARE
    g RECORD;
BEGIN
    IF current_user = 'motel_app' AND NEW.operador_id IS DISTINCT FROM app_operador() THEN
        RAISE EXCEPTION 'Clientes perdidos: se registran solo a nombre del usuario de la sesion.';
    END IF;
    SELECT estado, operador_id INTO g FROM guardias WHERE id = NEW.guardia_id;
    IF g.estado IS DISTINCT FROM 'Abierta' OR g.operador_id IS DISTINCT FROM NEW.operador_id THEN
        RAISE EXCEPTION 'Clientes perdidos: la guardia % no es la guardia abierta de quien registra.', NEW.guardia_id;
    END IF;
    NEW.creado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_cliente_perdido
BEFORE INSERT ON clientes_perdidos
FOR EACH ROW
EXECUTE FUNCTION check_cliente_perdido();

ALTER TABLE eventos_habitacion ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON eventos_habitacion TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());
ALTER TABLE clientes_perdidos ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON clientes_perdidos TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());

-- Solo agregado: sin UPDATE ni DELETE para la aplicacion.
GRANT SELECT, INSERT ON eventos_habitacion, clientes_perdidos TO motel_app;
GRANT USAGE ON SEQUENCE eventos_habitacion_id_seq, clientes_perdidos_id_seq TO motel_app;
