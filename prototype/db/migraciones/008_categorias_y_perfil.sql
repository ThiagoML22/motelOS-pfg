-- db/migraciones/008_categorias_y_perfil.sql
-- Demostracion del Sprint 4 (copia local, no entregada): categorias de habitacion con su propia tarifa, y perfil
-- de cada usuario (nombre visible y clave propia). Se aplica con el usuario dueno de las tablas, despues de la 007.
--
-- Categorias: cada establecimiento define las suyas (Simple, Especial, VIP...), con nombre, descripcion y color. Cada
-- categoria tiene a lo sumo una tarifa vigente; una habitacion pertenece a una categoria y el turno que se abre en ella
-- toma la tarifa vigente de esa categoria. La regla de la migracion 005 no cambia: una tarifa no se edita, se
-- reemplaza, y el turno conserva la suya (RN-DER-06), aunque despues se cambie la tarifa o la categoria de la habitacion.

-- ---------------------------------------------------------------------------------------------------
-- Categorias de habitacion
-- ---------------------------------------------------------------------------------------------------
CREATE TABLE categorias_habitacion (
    id SERIAL PRIMARY KEY,
    establecimiento_id INTEGER NOT NULL DEFAULT app_establecimiento() REFERENCES establecimientos(id),
    nombre VARCHAR(40) NOT NULL CHECK (length(trim(nombre)) >= 2),
    descripcion VARCHAR(160),
    color VARCHAR(7) NOT NULL DEFAULT '#244473' CHECK (color ~ '^#[0-9a-fA-F]{6}$'),
    orden INTEGER NOT NULL DEFAULT 0,
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    creada_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT categorias_nombre_por_establecimiento UNIQUE (establecimiento_id, nombre),
    CONSTRAINT categorias_est_id UNIQUE (establecimiento_id, id)
);

-- Cada establecimiento existente arranca con la categoria Simple, que recibe su tarifa y todas sus habitaciones.
INSERT INTO categorias_habitacion (establecimiento_id, nombre, descripcion, color, orden)
SELECT id, 'Simple', 'Habitacion estandar', '#244473', 1 FROM establecimientos;

ALTER TABLE habitaciones ADD COLUMN categoria_id INTEGER;
UPDATE habitaciones h SET categoria_id = c.id
  FROM categorias_habitacion c WHERE c.establecimiento_id = h.establecimiento_id;
ALTER TABLE habitaciones ALTER COLUMN categoria_id SET NOT NULL;
ALTER TABLE habitaciones ADD CONSTRAINT habitaciones_categoria_mismo_est
    FOREIGN KEY (establecimiento_id, categoria_id) REFERENCES categorias_habitacion (establecimiento_id, id);

-- Tarifas: cada una es de una categoria. Tolerancia y tope (precio maximo de la estadia, por ejemplo un pernocte)
-- quedan configurables; el tope es opcional y, si existe, no puede ser menor que la estadia base.
ALTER TABLE tarifas ADD COLUMN categoria_id INTEGER;
UPDATE tarifas t SET categoria_id = c.id
  FROM categorias_habitacion c WHERE c.establecimiento_id = t.establecimiento_id;
ALTER TABLE tarifas ALTER COLUMN categoria_id SET NOT NULL;
ALTER TABLE tarifas ADD CONSTRAINT tarifas_categoria_mismo_est
    FOREIGN KEY (establecimiento_id, categoria_id) REFERENCES categorias_habitacion (establecimiento_id, id);
ALTER TABLE tarifas ADD COLUMN tope NUMERIC(10, 2);
ALTER TABLE tarifas ADD CONSTRAINT tarifa_tope_valido CHECK (tope IS NULL OR tope >= tarifa_base);

-- Una tarifa vigente por categoria (antes, por establecimiento).
DROP INDEX tarifas_una_vigente;
CREATE UNIQUE INDEX tarifas_una_vigente ON tarifas (establecimiento_id, categoria_id) WHERE vigente;

-- Una categoria con habitaciones activas no se desactiva: primero se reasignan sus habitaciones.
CREATE OR REPLACE FUNCTION check_categoria_baja()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.activa AND NOT NEW.activa
       AND EXISTS (SELECT 1 FROM habitaciones WHERE categoria_id = OLD.id AND activa) THEN
        RAISE EXCEPTION 'Categorias: % tiene habitaciones activas; reasignelas antes de darla de baja.', OLD.nombre;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_categoria_baja
BEFORE UPDATE ON categorias_habitacion
FOR EACH ROW
EXECUTE FUNCTION check_categoria_baja();

-- Una habitacion solo se asigna a una categoria activa. Corre con los permisos del dueno para que el control de RLS
-- (WITH CHECK) sea el que rechace una fila de otro establecimiento; que la categoria sea del mismo establecimiento lo
-- garantiza la clave foranea compuesta.
CREATE OR REPLACE FUNCTION check_habitacion_categoria()
RETURNS TRIGGER
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF (TG_OP = 'INSERT' OR NEW.categoria_id IS DISTINCT FROM OLD.categoria_id)
       AND NOT EXISTS (SELECT 1 FROM categorias_habitacion WHERE id = NEW.categoria_id AND activa) THEN
        RAISE EXCEPTION 'Categorias: la categoria % no esta activa.', NEW.categoria_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_habitacion_categoria
BEFORE INSERT OR UPDATE ON habitaciones
FOR EACH ROW
EXECUTE FUNCTION check_habitacion_categoria();

ALTER TABLE categorias_habitacion ENABLE ROW LEVEL SECURITY;
CREATE POLICY aislamiento_establecimiento ON categorias_habitacion TO motel_app
    USING (establecimiento_id = app_establecimiento())
    WITH CHECK (establecimiento_id = app_establecimiento());

GRANT SELECT, INSERT ON categorias_habitacion TO motel_app;
GRANT UPDATE (nombre, descripcion, color, orden, activa) ON categorias_habitacion TO motel_app;
GRANT USAGE ON SEQUENCE categorias_habitacion_id_seq TO motel_app;
GRANT INSERT (categoria_id, tope) ON tarifas TO motel_app;

-- ---------------------------------------------------------------------------------------------------
-- Perfil: cada usuario cambia su nombre visible y su clave; la gerencia restablece la clave de un conserje.
-- motel_app sigue sin permiso de UPDATE sobre hash_clave (migracion 005). Las dos funciones de abajo son la unica via
-- y solo actuan sobre el usuario de la sesion (app.operador_id, que la aplicacion toma del token firmado) o, para la
-- gerencia, sobre un conserje de su propio establecimiento. La clave actual la verifica la aplicacion (argon2id): la
-- base no puede verificar ese hash.
-- ---------------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app_operador() RETURNS INTEGER AS $$
    SELECT coalesce(nullif(current_setting('app.operador_id', true), ''), '-1')::INTEGER;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION cambiar_clave_propia(p_hash_nuevo TEXT)
RETURNS VOID
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    UPDATE operadores
       SET hash_clave = p_hash_nuevo, intentos_fallidos = 0, bloqueado_hasta = NULL
     WHERE id = app_operador() AND coalesce(establecimiento_id, 0) = app_establecimiento() AND activo;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Perfil: la sesion no corresponde a un usuario activo.';
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION restablecer_clave_conserje(p_operador_id INTEGER, p_hash_nuevo TEXT)
RETURNS VOID
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM operadores WHERE id = app_operador() AND establecimiento_id = app_establecimiento()
                   AND rol = 'ADMINISTRADOR' AND activo) THEN
        RAISE EXCEPTION 'Perfil: solo la gerencia del establecimiento restablece claves.';
    END IF;
    UPDATE operadores
       SET hash_clave = p_hash_nuevo, intentos_fallidos = 0, bloqueado_hasta = NULL
     WHERE id = p_operador_id AND establecimiento_id = app_establecimiento() AND rol = 'OPERADOR';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Perfil: el usuario % no es un conserje de este establecimiento.', p_operador_id;
    END IF;
END;
$$ LANGUAGE plpgsql;

REVOKE ALL ON FUNCTION cambiar_clave_propia(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION restablecer_clave_conserje(INTEGER, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION cambiar_clave_propia(TEXT) TO motel_app;
GRANT EXECUTE ON FUNCTION restablecer_clave_conserje(INTEGER, TEXT) TO motel_app;
GRANT EXECUTE ON FUNCTION app_operador() TO motel_app;

-- El nombre visible lo cambia cada usuario desde su perfil (no es un dato sensible ni da permisos).
GRANT UPDATE (nombre_visible) ON operadores TO motel_app;

-- El resumen de la plataforma suma las categorias de cada establecimiento.
DROP FUNCTION resumen_plataforma();
CREATE OR REPLACE FUNCTION resumen_plataforma()
RETURNS TABLE (
    establecimiento_id INTEGER,
    habitaciones BIGINT,
    ocupadas BIGINT,
    usuarios BIGINT,
    turnos_ultimas_24h BIGINT,
    cobrado_ultimas_24h NUMERIC,
    guardia_abierta BOOLEAN,
    categorias BIGINT
)
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF app_establecimiento() <> 0 THEN
        RAISE EXCEPTION 'Plataforma: el resumen es solo para la plataforma.';
    END IF;
    RETURN QUERY
    SELECT e.id,
           (SELECT count(*) FROM habitaciones h WHERE h.establecimiento_id = e.id AND h.activa),
           (SELECT count(*) FROM habitaciones h WHERE h.establecimiento_id = e.id AND h.estado = 'Ocupada'),
           (SELECT count(*) FROM operadores o WHERE o.establecimiento_id = e.id AND o.activo),
           (SELECT count(*) FROM turnos t
             WHERE t.establecimiento_id = e.id AND t.hora_inicio >= now() - interval '24 hours'),
           (SELECT coalesce(sum(p.monto), 0) FROM pagos p
             WHERE p.establecimiento_id = e.id AND p.created_at >= now() - interval '24 hours'),
           EXISTS (SELECT 1 FROM guardias g WHERE g.establecimiento_id = e.id AND g.estado = 'Abierta'),
           (SELECT count(*) FROM categorias_habitacion c WHERE c.establecimiento_id = e.id AND c.activa)
      FROM establecimientos e;
END;
$$ LANGUAGE plpgsql;
REVOKE ALL ON FUNCTION resumen_plataforma() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION resumen_plataforma() TO motel_app;

-- La categoria del registro de actividad incluye las categorias de habitacion.
ALTER TABLE registro_actividad DROP CONSTRAINT registro_actividad_categoria_check;
ALTER TABLE registro_actividad ADD CONSTRAINT registro_actividad_categoria_check
    CHECK (categoria IN ('INVENTARIO', 'TARIFA', 'CAJA', 'HABITACION', 'PERSONAL', 'ESTABLECIMIENTO', 'PERFIL'));
