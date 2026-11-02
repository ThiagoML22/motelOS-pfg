-- Verifica (RF-11, RN-DER-06) el panel de configuracion con el rol de la aplicacion, motel_app:
-- da de alta solo conserjes (no elige el rol), no da de baja a la gerencia ni a quien tiene la guardia abierta,
-- no edita una tarifa existente ni deja dos vigentes, no da de baja una habitacion con un turno en curso y
-- cambia el fondo de cambio sin tocar la guardia abierta.
-- Falla con error si alguna restriccion no se cumple. Corre dentro de una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_configuracion.sql  (como dueno)
BEGIN;
DO $$
DECLARE
    gerencia_id integer;
    conserje_id integer;
    nuevo_id integer;
    gid integer;
    tarifa_vieja integer;
    hab_nueva integer;
    rol_nuevo varchar(20);
    fondo_guardia numeric;
    bloqueado boolean;
BEGIN
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol)
    VALUES ('verif.gerencia', 'Gerencia', 'x', 'ADMINISTRADOR') RETURNING id INTO gerencia_id;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave)
    VALUES ('verif.conserje', 'Conserje', 'x') RETURNING id INTO conserje_id;
    INSERT INTO guardias (operador_id, franja, fondo_inicial) VALUES (conserje_id, '06:00', 25000) RETURNING id INTO gid;
    INSERT INTO turnos (habitacion_id, tarifa_id, tarifa_base, total_general, estado,
                        operador_apertura_id, guardia_apertura_id)
    VALUES (1, 1, 8000, 8000, 'En Curso', conserje_id, gid);

    SET LOCAL ROLE motel_app;

    -- Alta de un conserje: el rol lo pone la base (OPERADOR); motel_app no puede elegirlo.
    INSERT INTO operadores (usuario, nombre_visible, hash_clave) VALUES ('verif.nuevo', 'Nuevo', 'x')
    RETURNING id, rol INTO nuevo_id, rol_nuevo;
    IF rol_nuevo <> 'OPERADOR' THEN RAISE EXCEPTION 'El alta desde la aplicacion no creo un OPERADOR'; END IF;

    bloqueado := false;
    BEGIN INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.intruso', 'X', 'x', 'ADMINISTRADOR');
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo crear un ADMINISTRADOR'; END IF;

    -- Baja logica de un conserje sin guardia abierta.
    UPDATE operadores SET activo = false WHERE id = nuevo_id;

    bloqueado := false;
    BEGIN UPDATE operadores SET activo = false WHERE id = gerencia_id;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo dar de baja a la gerencia'; END IF;

    bloqueado := false;
    BEGIN UPDATE operadores SET activo = false WHERE id = conserje_id;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app dio de baja a un conserje con su guardia abierta'; END IF;

    -- Tarifas: una nueva reemplaza a la vigente; la anterior no se edita ni se borra.
    SELECT id INTO tarifa_vieja FROM tarifas WHERE vigente;
    UPDATE tarifas SET vigente = false WHERE id = tarifa_vieja;
    INSERT INTO tarifas (nombre, tarifa_base, tarifa_fraccion, creada_por_id) VALUES ('Verificacion', 9000, 2500, gerencia_id);

    bloqueado := false;
    BEGIN UPDATE tarifas SET tarifa_base = 1 WHERE id = tarifa_vieja;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo editar el importe de una tarifa existente'; END IF;

    bloqueado := false;
    BEGIN DELETE FROM tarifas WHERE id = tarifa_vieja;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo borrar una tarifa'; END IF;

    bloqueado := false;
    BEGIN UPDATE tarifas SET vigente = true WHERE id = tarifa_vieja;
    EXCEPTION WHEN unique_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Quedaron dos tarifas vigentes'; END IF;

    -- Habitaciones: alta, baja logica; la ocupada no se da de baja ni cambia de numero; no se borran.
    INSERT INTO habitaciones (numero, estado) VALUES (999, 'Libre') RETURNING id INTO hab_nueva;
    UPDATE habitaciones SET activa = false WHERE id = hab_nueva;

    bloqueado := false;
    BEGIN UPDATE habitaciones SET activa = false WHERE id = 1;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se dio de baja una habitacion con un turno en curso'; END IF;

    bloqueado := false;
    BEGIN UPDATE habitaciones SET numero = 998 WHERE id = 1;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Cambio de numero una habitacion con un turno en curso'; END IF;

    bloqueado := false;
    BEGIN DELETE FROM habitaciones WHERE id = hab_nueva;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo borrar una habitacion'; END IF;

    -- Fondo de cambio: el cambio no altera la guardia ya abierta (RN-DER-06).
    UPDATE configuracion_caja SET fondo_cambio = 30000, actualizado_por_id = gerencia_id;
    SELECT fondo_inicial INTO fondo_guardia FROM guardias WHERE id = gid;
    IF fondo_guardia <> 25000 THEN RAISE EXCEPTION 'El cambio de fondo altero la guardia abierta'; END IF;

    bloqueado := false;
    BEGIN INSERT INTO configuracion_caja (id, fondo_cambio) VALUES (2, 1);
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'motel_app pudo agregar otra fila de configuracion'; END IF;

    RESET ROLE;
    RAISE NOTICE 'Panel verificado: motel_app crea solo conserjes, protege a la gerencia, no edita tarifas usadas ni borra historia';
END $$;
ROLLBACK;
