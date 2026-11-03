-- db/migraciones/010_pedidos_reposicion.sql
-- Demostracion del Sprint 4 (copia local, no entregada): pedidos de reposicion a proveedores.
-- Se aplica con el usuario dueno de las tablas, despues de 009_personalizacion_y_novedades.sql.
--
-- La gerencia arma un pedido (por ejemplo, con la reposicion sugerida por la inteligencia) y lo manda al proveedor.
-- Cuando llega la mercaderia, el conserje o la gerencia lo recibe con las cantidades reales: se suman al stock y quedan
-- en el registro de actividad. Un pedido no se borra y solo pasa una vez de Pendiente a Recibido o Anulado.

CREATE TABLE pedidos_reposicion (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    creado_por_id INTEGER NOT NULL,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    proveedor VARCHAR(80),
    nota VARCHAR(300),
    estado VARCHAR(10) NOT NULL DEFAULT 'Pendiente' CHECK (estado IN ('Pendiente', 'Recibido', 'Anulado')),
    cerrado_por_id INTEGER,
    cerrado_en TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pedidos_cierre_coherente CHECK ((estado = 'Pendiente') = (cerrado_en IS NULL AND cerrado_por_id IS NULL)),
    CONSTRAINT pedidos_est_id UNIQUE (establecimiento_id, id),
    CONSTRAINT pedidos_creador_mismo_est FOREIGN KEY (establecimiento_id, creado_por_id)
        REFERENCES operadores (establecimiento_id, id),
    CONSTRAINT pedidos_cierre_mismo_est FOREIGN KEY (establecimiento_id, cerrado_por_id)
        REFERENCES operadores (establecimiento_id, id)
);

CREATE TABLE pedido_items (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    pedido_id INTEGER NOT NULL,
    articulo_id INTEGER NOT NULL,
    cantidad INTEGER NOT NULL CHECK (cantidad > 0 AND cantidad <= 10000),
    recibida INTEGER CHECK (recibida >= 0 AND recibida <= 10000),
    CONSTRAINT pedido_items_un_articulo UNIQUE (pedido_id, articulo_id),
    CONSTRAINT pedido_items_pedido_mismo_est FOREIGN KEY (establecimiento_id, pedido_id)
        REFERENCES pedidos_reposicion (establecimiento_id, id),
    CONSTRAINT pedido_items_articulo_mismo_est FOREIGN KEY (establecimiento_id, articulo_id)
        REFERENCES articulos (establecimiento_id, id)
);

CREATE INDEX pedidos_recientes ON pedidos_reposicion (establecimiento_id, creado_en DESC);

-- Un pedido no se borra; cerrado (Recibido o Anulado) no cambia mas, y sus datos de alta nunca cambian.
CREATE OR REPLACE FUNCTION check_pedido()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Pedidos: un pedido no se elimina; se anula.';
    END IF;
    IF OLD.estado <> 'Pendiente' THEN
        RAISE EXCEPTION 'Pedidos: el pedido % ya esta %.', OLD.id, lower(OLD.estado);
    END IF;
    IF (NEW.establecimiento_id, NEW.creado_por_id, NEW.creado_en, NEW.proveedor, NEW.nota)
       IS DISTINCT FROM (OLD.establecimiento_id, OLD.creado_por_id, OLD.creado_en, OLD.proveedor, OLD.nota) THEN
        RAISE EXCEPTION 'Pedidos: los datos del pedido no se modifican.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_pedido
BEFORE UPDATE OR DELETE ON pedidos_reposicion
FOR EACH ROW
EXECUTE FUNCTION check_pedido();

-- De un item solo se anota lo recibido, una vez y mientras el pedido esta pendiente.
CREATE OR REPLACE FUNCTION check_pedido_item()
RETURNS TRIGGER AS $$
DECLARE
    estado_pedido VARCHAR(10);
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Pedidos: los articulos de un pedido no se eliminan.';
    END IF;
    IF (NEW.establecimiento_id, NEW.pedido_id, NEW.articulo_id, NEW.cantidad)
       IS DISTINCT FROM (OLD.establecimiento_id, OLD.pedido_id, OLD.articulo_id, OLD.cantidad) THEN
        RAISE EXCEPTION 'Pedidos: lo pedido no se modifica.';
    END IF;
    IF OLD.recibida IS NOT NULL THEN
        RAISE EXCEPTION 'Pedidos: la recepcion de este articulo ya se registro.';
    END IF;
    SELECT estado INTO estado_pedido FROM pedidos_reposicion WHERE id = NEW.pedido_id;
    IF estado_pedido IS DISTINCT FROM 'Pendiente' THEN
        RAISE EXCEPTION 'Pedidos: el pedido % no esta pendiente.', NEW.pedido_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_pedido_item
BEFORE UPDATE OR DELETE ON pedido_items
FOR EACH ROW
EXECUTE FUNCTION check_pedido_item();

ALTER TABLE pedidos_reposicion ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON pedidos_reposicion TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());
ALTER TABLE pedido_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON pedido_items TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());

GRANT SELECT, INSERT ON pedidos_reposicion, pedido_items TO motel_app;
GRANT UPDATE (estado, cerrado_por_id, cerrado_en) ON pedidos_reposicion TO motel_app;
GRANT UPDATE (recibida) ON pedido_items TO motel_app;
GRANT USAGE ON SEQUENCE pedidos_reposicion_id_seq, pedido_items_id_seq TO motel_app;
