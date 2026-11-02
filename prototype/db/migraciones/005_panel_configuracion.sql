-- db/migraciones/005_panel_configuracion.sql
-- Prototipo v3 (AE4): panel de configuracion de la gerencia (RF-11 ampliado, acta del 27/10/2026): tarifa y
-- fraccion, articulos y precios, habitaciones, alta y baja de conserjes y fondo de cambio.
-- Regla: RN-DER-06 (un cambio rige hacia adelante; lo ya registrado conserva su valor).
-- Se aplica con el usuario dueno de las tablas, despues de 004_un_turno_por_habitacion.sql.
--
-- Criterio de diseno: la aplicacion sigue conectandose con motel_app y recibe solo los permisos que el panel
-- necesita, por columna. Lo que no se concede no se puede hacer aunque alguien logre ejecutar SQL con esa
-- conexion: crear un ADMINISTRADOR, cambiar un rol o una clave, editar una tarifa ya usada o borrar historia.
-- Se descartaron dos alternativas: funciones SECURITY DEFINER (mas codigo en la base, que las pruebas en
-- SQLite no ejecutan) y un segundo rol de administracion (la misma aplicacion guardaria las dos claves, de
-- modo que quien comprometa la aplicacion obtiene ambas).

-- ---------------------------------------------------------------------------------------------------
-- Tarifas. Una tarifa ya usada no se edita: cambiar la tarifa es crear una nueva y dejar la anterior no
-- vigente. Los turnos guardan tarifa_id y tarifa_base, de modo que un turno abierto o cerrado se liquida
-- siempre con la tarifa con la que empezo (criterio de RF-11).
-- ---------------------------------------------------------------------------------------------------
ALTER TABLE tarifas
    ADD COLUMN vigente_desde TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN creada_por_id INTEGER REFERENCES operadores(id);
ALTER TABLE tarifas ADD CONSTRAINT tarifa_valores_validos CHECK (
    tarifa_base > 0 AND estadia_base_min > 0 AND tolerancia_min >= 0 AND fraccion_min > 0 AND tarifa_fraccion >= 0);

-- A lo sumo una tarifa vigente: dos cambios simultaneos no dejan dos tarifas que compitan.
CREATE UNIQUE INDEX tarifas_una_vigente ON tarifas (vigente) WHERE vigente;

-- ---------------------------------------------------------------------------------------------------
-- Articulos y habitaciones: baja logica. Los consumos y los turnos los referencian, por eso no se borran.
-- ---------------------------------------------------------------------------------------------------
ALTER TABLE articulos ADD COLUMN activo BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE articulos ADD CONSTRAINT articulo_precio_valido CHECK (precio_unitario >= 0);

ALTER TABLE habitaciones ADD COLUMN activa BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE habitaciones ADD CONSTRAINT habitacion_numero_valido CHECK (numero > 0);

-- Una habitacion con un turno en curso no se da de baja ni cambia de numero.
CREATE OR REPLACE FUNCTION check_habitacion_configuracion()
RETURNS TRIGGER AS $$
BEGIN
    IF (NEW.activa IS DISTINCT FROM OLD.activa AND NOT NEW.activa) OR NEW.numero <> OLD.numero THEN
        IF EXISTS (SELECT 1 FROM turnos WHERE habitacion_id = OLD.id AND estado = 'En Curso') THEN
            RAISE EXCEPTION 'RF-11: La habitacion % tiene un turno en curso.', OLD.numero;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_habitacion_configuracion
BEFORE UPDATE ON habitaciones
FOR EACH ROW
EXECUTE FUNCTION check_habitacion_configuracion();

-- ---------------------------------------------------------------------------------------------------
-- Conserjes. motel_app puede dar de alta operadores sin elegir el rol: la columna toma su valor por defecto,
-- OPERADOR. La baja es logica (activo) y no alcanza a la gerencia ni a quien tiene su guardia abierta.
-- ---------------------------------------------------------------------------------------------------
ALTER TABLE operadores ALTER COLUMN rol SET DEFAULT 'OPERADOR';

CREATE OR REPLACE FUNCTION check_operador_baja()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.activo IS DISTINCT FROM OLD.activo THEN
        IF OLD.rol = 'ADMINISTRADOR' THEN
            RAISE EXCEPTION 'RF-11: La gerencia no se da de alta ni de baja desde la aplicacion.';
        END IF;
        IF NOT NEW.activo AND EXISTS (SELECT 1 FROM guardias WHERE operador_id = OLD.id AND estado = 'Abierta') THEN
            RAISE EXCEPTION 'RF-11: El conserje tiene su guardia abierta; se cierra antes de darlo de baja.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_operador_baja
BEFORE UPDATE ON operadores
FOR EACH ROW
EXECUTE FUNCTION check_operador_baja();

-- ---------------------------------------------------------------------------------------------------
-- Fondo de cambio de la caja (acta del 19/10/2026: $25.000). Una sola fila. La guardia copia el monto al
-- abrirse (guardias.fondo_inicial, que no cambia despues): el monto nuevo rige desde la guardia siguiente.
-- ---------------------------------------------------------------------------------------------------
CREATE TABLE configuracion_caja (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    fondo_cambio NUMERIC(12, 2) NOT NULL CHECK (fondo_cambio >= 0),
    actualizado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_por_id INTEGER REFERENCES operadores(id)
);
INSERT INTO configuracion_caja (id, fondo_cambio) VALUES (1, 25000);

-- ---------------------------------------------------------------------------------------------------
-- Permisos de motel_app para el panel (por columna donde corresponde)
-- ---------------------------------------------------------------------------------------------------
GRANT INSERT (nombre, tarifa_base, estadia_base_min, tolerancia_min, fraccion_min, tarifa_fraccion, vigente,
              vigente_desde, creada_por_id) ON tarifas TO motel_app;
GRANT UPDATE (vigente) ON tarifas TO motel_app;
GRANT USAGE ON SEQUENCE tarifas_id_seq TO motel_app;

GRANT INSERT ON habitaciones TO motel_app;
GRANT USAGE ON SEQUENCE habitaciones_id_seq TO motel_app;

-- Sin la columna rol: el alta solo crea conserjes. Sin hash_clave en UPDATE: la clave no se cambia.
-- El ORM inserta todas las columnas del modelo salvo las que tienen valor por defecto en la base (rol), por eso
-- figuran bloqueado_hasta y ultimo_acceso (van en NULL; motel_app ya las actualiza desde la migracion 002).
GRANT INSERT (usuario, nombre_visible, hash_clave, activo, intentos_fallidos, bloqueado_hasta, ultimo_acceso,
              creado_en) ON operadores TO motel_app;
GRANT UPDATE (activo) ON operadores TO motel_app;
GRANT USAGE ON SEQUENCE operadores_id_seq TO motel_app;

GRANT SELECT ON configuracion_caja TO motel_app;
GRANT UPDATE (fondo_cambio, actualizado_en, actualizado_por_id) ON configuracion_caja TO motel_app;
