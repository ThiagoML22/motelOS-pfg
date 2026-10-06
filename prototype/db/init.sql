-- db/init.sql

CREATE TABLE habitaciones (
    id SERIAL PRIMARY KEY,
    numero INTEGER UNIQUE NOT NULL,
    estado VARCHAR(20) NOT NULL CHECK (estado IN ('Libre', 'Ocupada', 'En Limpieza', 'Mantenimiento'))
);

CREATE TABLE tarifas (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) UNIQUE NOT NULL,
    tarifa_base NUMERIC(10, 2) NOT NULL,
    estadia_base_min INTEGER NOT NULL DEFAULT 120,
    tolerancia_min INTEGER NOT NULL DEFAULT 0,
    fraccion_min INTEGER NOT NULL DEFAULT 30,
    tarifa_fraccion NUMERIC(10, 2) NOT NULL,
    vigente BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE turnos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    habitacion_id INTEGER NOT NULL REFERENCES habitaciones(id),
    tarifa_id INTEGER NOT NULL REFERENCES tarifas(id),
    tipo_cliente VARCHAR(20) NOT NULL DEFAULT 'Auto' CHECK (tipo_cliente IN ('Auto', 'Moto', 'Peaton')),
    hora_inicio TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hora_fin TIMESTAMP WITH TIME ZONE,
    tarifa_base NUMERIC(10, 2) NOT NULL,
    total_sobreturno NUMERIC(10, 2) NOT NULL DEFAULT 0,
    total_consumos NUMERIC(10, 2) NOT NULL DEFAULT 0,
    total_general NUMERIC(10, 2) NOT NULL,
    estado VARCHAR(20) NOT NULL CHECK (estado IN ('En Curso', 'FINALIZADO', 'Anulado'))
);

-- RNF-08: la patente es un dato operativo y vive fuera del turno inmutable. La aplicacion la elimina
-- dentro de las 24 h posteriores al cierre del turno (RETENCION_PATENTE_HORAS); el turno, sus pagos y sus
-- consumos no se tocan.
CREATE TABLE estadias_activas (
    turno_id UUID PRIMARY KEY REFERENCES turnos(id),
    identificador_vehicular VARCHAR(50) NOT NULL
);

CREATE TABLE articulos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) UNIQUE NOT NULL,
    descripcion VARCHAR(255) NOT NULL,
    precio_unitario NUMERIC(10, 2) NOT NULL,
    stock_actual INTEGER NOT NULL CHECK (stock_actual >= 0),
    categoria VARCHAR(50)
);

CREATE TABLE detalles_consumo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turno_id UUID NOT NULL REFERENCES turnos(id),
    articulo_id INTEGER NOT NULL REFERENCES articulos(id),
    cantidad INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario NUMERIC(10, 2) NOT NULL,
    subtotal NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pagos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turno_id UUID NOT NULL REFERENCES turnos(id),
    monto NUMERIC(10, 2) NOT NULL,
    medio_pago VARCHAR(50) NOT NULL CHECK (medio_pago IN ('EFECTIVO', 'MERCADO_PAGO', 'POSNET')),
    comprobante_referencia VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Sin Row-Level Security: el prototipo atiende a un solo establecimiento y una politica
-- "USING (true)" no restringiria ninguna fila. La inmutabilidad la imponen los triggers de abajo.
-- Alcance de esa garantia: ninguna sentencia de la aplicacion altera un turno cerrado. El dueno de las
-- tablas puede deshabilitar un trigger, por eso la aplicacion se conecta con un rol distinto (motel_app,
-- al final de este archivo) que no es dueno de las tablas y no puede alterarlas ni deshabilitar triggers.

-- Disparador para asegurar inmutabilidad de turnos cerrados/anulados (Append-Only Log)
CREATE OR REPLACE FUNCTION check_turno_inmutable()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.estado IN ('FINALIZADO', 'Anulado') THEN
        RAISE EXCEPTION 'RN-RES-01: No se puede modificar ni eliminar un turno finalizado o anulado.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_check_turno_inmutable
BEFORE UPDATE OR DELETE ON turnos
FOR EACH ROW
EXECUTE FUNCTION check_turno_inmutable();

-- Los pagos son un registro de solo agregado: no admiten UPDATE ni DELETE.
CREATE OR REPLACE FUNCTION check_pago_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'RN-RES-01: Los pagos registrados no se pueden modificar ni eliminar.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_pagos_append_only
BEFORE UPDATE OR DELETE ON pagos
FOR EACH ROW
EXECUTE FUNCTION check_pago_append_only();

-- Los consumos de un turno cerrado o anulado tampoco pueden alterarse.
CREATE OR REPLACE FUNCTION check_consumo_inmutable()
RETURNS TRIGGER AS $$
DECLARE
    estado_turno VARCHAR(20);
BEGIN
    SELECT estado INTO estado_turno FROM turnos WHERE id = OLD.turno_id;
    IF estado_turno IN ('FINALIZADO', 'Anulado') THEN
        RAISE EXCEPTION 'RN-RES-01: No se puede modificar ni eliminar el consumo de un turno finalizado o anulado.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_consumos_inmutables
BEFORE UPDATE OR DELETE ON detalles_consumo
FOR EACH ROW
EXECUTE FUNCTION check_consumo_inmutable();

-- Seeds iniciales
-- Tarifa estandar: estadia base de 120 min por $8.000 y, superada, fracciones de 30 min a $2.500 (sin tolerancia).
INSERT INTO tarifas (nombre, tarifa_base, estadia_base_min, tolerancia_min, fraccion_min, tarifa_fraccion, vigente)
VALUES ('Estandar', 8000, 120, 0, 30, 2500, TRUE);

INSERT INTO habitaciones (numero, estado) VALUES 
(1, 'Libre'), (2, 'Libre'), (3, 'Libre'), (4, 'Libre'), (5, 'Libre'), 
(6, 'Libre'), (7, 'Libre'), (8, 'Libre'), (9, 'Libre'), (10, 'Libre'), 
(11, 'Libre'), (12, 'Libre'), (13, 'Libre');

INSERT INTO articulos (codigo, descripcion, precio_unitario, stock_actual, categoria) VALUES
('MIN-001', 'Agua Mineral 500ml', 800, 10, 'Bebidas'),
('MIN-002', 'Bebida Energética', 1200, 8, 'Bebidas'),
('MIN-003', 'Cerveza Lata 473ml', 1800, 12, 'Bebidas'),
('SNA-001', 'Papas Fritas Lays 90g', 1500, 5, 'Snacks');

-- Roles (RNF-08 / RNF-01): el usuario que ejecuta este archivo es el dueno de las tablas y se reserva para
-- migraciones y datos iniciales. La aplicacion usa motel_app: sin propiedad de las tablas, sin permiso para
-- ALTER TABLE ni para deshabilitar triggers, y con los privilegios minimos de cada tabla.
-- La clave de abajo es solo para el entorno de demostracion: se cambia al desplegar.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'motel_app') THEN
        CREATE ROLE motel_app LOGIN PASSWORD 'motel_app' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END $$;
GRANT USAGE ON SCHEMA public TO motel_app;
GRANT SELECT, UPDATE ON habitaciones, articulos TO motel_app;
GRANT SELECT ON tarifas TO motel_app;
GRANT SELECT, INSERT, UPDATE ON turnos TO motel_app;
GRANT SELECT, INSERT ON detalles_consumo, pagos TO motel_app;
GRANT SELECT, INSERT, DELETE ON estadias_activas TO motel_app;
