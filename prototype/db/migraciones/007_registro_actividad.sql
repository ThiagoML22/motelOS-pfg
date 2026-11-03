-- db/migraciones/007_registro_actividad.sql
-- Demostracion del Sprint 4 (copia local, no entregada): registro de actividad para la gerencia.
-- Se aplica con el usuario dueno de las tablas, despues de 006_multiinquilino.sql.
--
-- Cada cambio de inventario (alta de un articulo, reposicion de stock, precio, baja) y de configuracion (tarifa,
-- fondo de cambio, habitaciones, conserjes, datos del establecimiento) deja una fila con quien lo hizo, en que
-- guardia y que cambio. Lo que hace un conserje queda "por revisar" hasta que la gerencia lo marca como visto.
-- El registro es de solo agregado: lo unico que cambia despues es la marca de revision, una vez.

CREATE TABLE registro_actividad (
    id BIGSERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    operador_id INTEGER NOT NULL,
    guardia_id INTEGER,
    categoria VARCHAR(20) NOT NULL
        CHECK (categoria IN ('INVENTARIO', 'TARIFA', 'CAJA', 'HABITACION', 'PERSONAL', 'ESTABLECIMIENTO')),
    accion VARCHAR(40) NOT NULL,
    descripcion VARCHAR(300) NOT NULL,
    articulo_id INTEGER,
    cantidad INTEGER,
    valor_anterior VARCHAR(80),
    valor_nuevo VARCHAR(80),
    requiere_revision BOOLEAN NOT NULL DEFAULT FALSE,
    revisado_por_id INTEGER,
    revisado_en TIMESTAMP WITH TIME ZONE,
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT actividad_revision_coherente CHECK ((revisado_por_id IS NULL) = (revisado_en IS NULL)),
    CONSTRAINT actividad_operador_mismo_est FOREIGN KEY (establecimiento_id, operador_id)
        REFERENCES operadores (establecimiento_id, id),
    CONSTRAINT actividad_guardia_mismo_est FOREIGN KEY (establecimiento_id, guardia_id)
        REFERENCES guardias (establecimiento_id, id),
    CONSTRAINT actividad_articulo_mismo_est FOREIGN KEY (establecimiento_id, articulo_id)
        REFERENCES articulos (establecimiento_id, id),
    CONSTRAINT actividad_revisor_mismo_est FOREIGN KEY (establecimiento_id, revisado_por_id)
        REFERENCES operadores (establecimiento_id, id)
);

CREATE INDEX registro_actividad_reciente ON registro_actividad (establecimiento_id, creado_en DESC);
CREATE INDEX registro_actividad_pendiente ON registro_actividad (establecimiento_id)
    WHERE requiere_revision AND revisado_en IS NULL;

-- Solo agregado: no se borra, y de una fila solo cambia la marca de revision, una vez y por la gerencia.
CREATE OR REPLACE FUNCTION check_registro_actividad()
RETURNS TRIGGER AS $$
DECLARE
    rol_revisor VARCHAR(20);
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Registro de actividad: las entradas no se eliminan.';
    END IF;
    IF OLD.revisado_en IS NOT NULL THEN
        RAISE EXCEPTION 'Registro de actividad: la entrada % ya fue revisada.', OLD.id;
    END IF;
    IF (NEW.establecimiento_id, NEW.operador_id, NEW.guardia_id, NEW.categoria, NEW.accion, NEW.descripcion,
        NEW.articulo_id, NEW.cantidad, NEW.valor_anterior, NEW.valor_nuevo, NEW.requiere_revision, NEW.creado_en)
       IS DISTINCT FROM
       (OLD.establecimiento_id, OLD.operador_id, OLD.guardia_id, OLD.categoria, OLD.accion, OLD.descripcion,
        OLD.articulo_id, OLD.cantidad, OLD.valor_anterior, OLD.valor_nuevo, OLD.requiere_revision, OLD.creado_en) THEN
        RAISE EXCEPTION 'Registro de actividad: solo cambia la marca de revision.';
    END IF;
    SELECT rol INTO rol_revisor FROM operadores WHERE id = NEW.revisado_por_id;
    IF rol_revisor IS DISTINCT FROM 'ADMINISTRADOR' THEN
        RAISE EXCEPTION 'Registro de actividad: solo la gerencia marca una entrada como revisada.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_registro_actividad
BEFORE UPDATE OR DELETE ON registro_actividad
FOR EACH ROW
EXECUTE FUNCTION check_registro_actividad();

ALTER TABLE registro_actividad ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON registro_actividad TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());

GRANT SELECT, INSERT ON registro_actividad TO motel_app;
GRANT UPDATE (revisado_por_id, revisado_en) ON registro_actividad TO motel_app;
GRANT USAGE ON SEQUENCE registro_actividad_id_seq TO motel_app;
