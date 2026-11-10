-- db/migraciones/013_pedidos_del_cliente.sql
-- Demostracion del Sprint 4 (copia local, no entregada): pedidos del cliente desde su habitacion.
-- Se aplica con el usuario dueno de las tablas, despues de 012_sellos_de_arqueo.sql.
--
-- Con el QR de su ticket, el cliente ve su tiempo y su cuenta y pide algo del minibar o avisa algo a la ventanilla, sin
-- cuenta ni datos personales. Un pedido no toca el stock ni la cuenta: es el conserje quien lo atiende, y recien ahi se
-- carga como consumo con todas sus reglas. No hay texto libre: solo un articulo o uno de los avisos fijos.

CREATE TABLE pedidos_cliente (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    turno_id UUID NOT NULL,
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('ARTICULO', 'TOALLAS', 'LLAMAR', 'SALIDA')),
    articulo_id INTEGER,
    cantidad INTEGER CHECK (cantidad BETWEEN 1 AND 5),
    estado VARCHAR(10) NOT NULL DEFAULT 'Pendiente' CHECK (estado IN ('Pendiente', 'Atendido', 'Rechazado')),
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atendido_por_id INTEGER,
    atendido_en TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pedidos_cliente_articulo_coherente
        CHECK ((tipo = 'ARTICULO') = (articulo_id IS NOT NULL AND cantidad IS NOT NULL)),
    CONSTRAINT pedidos_cliente_atencion_coherente
        CHECK ((estado = 'Pendiente') = (atendido_por_id IS NULL AND atendido_en IS NULL)),
    CONSTRAINT pedidos_cliente_turno_mismo_est FOREIGN KEY (establecimiento_id, turno_id)
        REFERENCES turnos (establecimiento_id, id),
    CONSTRAINT pedidos_cliente_articulo_mismo_est FOREIGN KEY (establecimiento_id, articulo_id)
        REFERENCES articulos (establecimiento_id, id),
    CONSTRAINT pedidos_cliente_atiende_mismo_est FOREIGN KEY (establecimiento_id, atendido_por_id)
        REFERENCES operadores (establecimiento_id, id)
);

CREATE INDEX pedidos_cliente_del_turno ON pedidos_cliente (establecimiento_id, turno_id);

-- Solo un turno en curso recibe pedidos, y la hora la pone la base.
CREATE OR REPLACE FUNCTION check_pedido_cliente_alta()
RETURNS TRIGGER AS $$
DECLARE
    estado_turno VARCHAR(20);
BEGIN
    SELECT estado INTO estado_turno FROM turnos WHERE id = NEW.turno_id;
    IF estado_turno IS DISTINCT FROM 'En Curso' THEN
        RAISE EXCEPTION 'Pedidos del cliente: el turno no esta en curso.';
    END IF;
    IF NEW.estado <> 'Pendiente' THEN
        RAISE EXCEPTION 'Pedidos del cliente: un pedido nuevo siempre empieza pendiente.';
    END IF;
    NEW.creado_en := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_pedido_cliente_alta
BEFORE INSERT ON pedidos_cliente
FOR EACH ROW
EXECUTE FUNCTION check_pedido_cliente_alta();

-- Se atiende una sola vez, a nombre del usuario de la sesion; lo pedido no cambia.
CREATE OR REPLACE FUNCTION check_pedido_cliente_atencion()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.estado <> 'Pendiente' THEN
        RAISE EXCEPTION 'Pedidos del cliente: el pedido % ya se atendio.', OLD.id;
    END IF;
    IF (NEW.establecimiento_id, NEW.turno_id, NEW.tipo, NEW.articulo_id, NEW.cantidad, NEW.creado_en)
       IS DISTINCT FROM (OLD.establecimiento_id, OLD.turno_id, OLD.tipo, OLD.articulo_id, OLD.cantidad, OLD.creado_en) THEN
        RAISE EXCEPTION 'Pedidos del cliente: lo pedido no se modifica.';
    END IF;
    IF current_user = 'motel_app' AND NEW.atendido_por_id IS DISTINCT FROM app_operador() THEN
        RAISE EXCEPTION 'Pedidos del cliente: se atienden solo a nombre del usuario de la sesion.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_pedido_cliente_atencion
BEFORE UPDATE ON pedidos_cliente
FOR EACH ROW
EXECUTE FUNCTION check_pedido_cliente_atencion();

ALTER TABLE pedidos_cliente ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON pedidos_cliente TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());

GRANT SELECT, INSERT ON pedidos_cliente TO motel_app;
GRANT UPDATE (estado, atendido_por_id, atendido_en) ON pedidos_cliente TO motel_app;
GRANT USAGE ON SEQUENCE pedidos_cliente_id_seq TO motel_app;
