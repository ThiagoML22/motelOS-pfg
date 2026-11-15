-- Verifica la migracion 019 con el rol de la aplicacion, motel_app: un equipo nuevo entra pendiente, solo la gerencia lo
-- autoriza o bloquea (a su nombre y con un nombre para el equipo), la marca no cambia, los intentos son de solo agregado
-- y se borran recien a los 90 dias, y otro establecimiento no ve nada. Corre en una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_equipos.sql  (como dueno)
SET app.establecimiento_id = '1';
BEGIN;
DO $$
DECLARE
    conserje integer;
    gerencia integer;
    equipo integer;
    filas integer;
    bloqueado boolean;
BEGIN
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.e', 'Conserje', 'x', 'OPERADOR')
    RETURNING id INTO conserje;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol) VALUES ('verif.g', 'Gerencia', 'x', 'ADMINISTRADOR')
    RETURNING id INTO gerencia;
    PERFORM set_config('app.operador_id', conserje::text, true);

    SET LOCAL ROLE motel_app;

    -- 1. Un conserje (o el inicio de sesion, sin usuario) deja el equipo pendiente; no puede autorizarlo.
    INSERT INTO equipos (huella, descripcion, ultima_ip, ultimo_operador_id)
    VALUES (repeat('a', 64), 'Chrome en Android (celular)', '192.168.0.50', conserje) RETURNING id INTO equipo;
    bloqueado := false;
    BEGIN INSERT INTO equipos (huella, descripcion, estado, nombre, decidido_por_id)
    VALUES (repeat('b', 64), 'Edge en Windows', 'AUTORIZADO', 'Mio', conserje);
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Un conserje dio de alta un equipo ya autorizado'; END IF;
    bloqueado := false;
    BEGIN UPDATE equipos SET estado = 'AUTORIZADO', nombre = 'Mio', decidido_por_id = conserje WHERE id = equipo;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Un conserje autorizo un equipo'; END IF;
    -- El uso si se actualiza.
    UPDATE equipos SET ultimo_uso = now(), ultima_ip = '192.168.0.51' WHERE id = equipo;

    -- 2. La gerencia autoriza, a su nombre y con un nombre para el equipo.
    PERFORM set_config('app.operador_id', gerencia::text, true);
    bloqueado := false;
    BEGIN UPDATE equipos SET estado = 'AUTORIZADO', decidido_por_id = gerencia WHERE id = equipo;
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se autorizo un equipo sin nombre'; END IF;
    bloqueado := false;
    BEGIN UPDATE equipos SET estado = 'AUTORIZADO', nombre = 'PC', decidido_por_id = conserje WHERE id = equipo;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'La gerencia autorizo a nombre de otro'; END IF;
    UPDATE equipos SET estado = 'AUTORIZADO', nombre = 'PC Ventanilla', decidido_por_id = gerencia WHERE id = equipo;
    SELECT count(*) INTO filas FROM equipos WHERE id = equipo AND estado = 'AUTORIZADO' AND decidido_en IS NOT NULL;
    IF filas <> 1 THEN RAISE EXCEPTION 'El equipo no quedo autorizado con la hora de la decision'; END IF;
    UPDATE equipos SET estado = 'BLOQUEADO', decidido_por_id = gerencia WHERE id = equipo;

    -- 3. La marca de un equipo no cambia, y un equipo no se borra.
    bloqueado := false;
    BEGIN UPDATE equipos SET huella = repeat('c', 64) WHERE id = equipo;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Cambio la marca de un equipo'; END IF;
    bloqueado := false;
    BEGIN DELETE FROM equipos WHERE id = equipo;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro un equipo'; END IF;

    -- 4. Los intentos: se agregan, no se editan, y uno reciente no se borra.
    INSERT INTO intentos_acceso (equipo_id, operador_id, clave_correcta, motivo, ip, descripcion)
    VALUES (equipo, conserje, true, 'EQUIPO', '192.168.0.50', 'Chrome en Android (celular)');
    bloqueado := false;
    BEGIN UPDATE intentos_acceso SET clave_correcta = false WHERE equipo_id = equipo;
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se edito un intento'; END IF;
    bloqueado := false;
    BEGIN DELETE FROM intentos_acceso WHERE equipo_id = equipo;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro un intento antes de los 90 dias'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO intentos_acceso (clave_correcta, motivo, descripcion) VALUES (false, 'OTRO', 'x');
    EXCEPTION WHEN check_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Entro un intento con un motivo desconocido'; END IF;

    -- 5. Otro establecimiento no ve los equipos ni los intentos.
    PERFORM set_config('app.establecimiento_id', '2', true);
    SELECT (SELECT count(*) FROM equipos WHERE huella = repeat('a', 64))
         + (SELECT count(*) FROM intentos_acceso WHERE equipo_id = equipo) INTO filas;
    IF filas <> 0 THEN RAISE EXCEPTION 'Otro establecimiento ve % filas de equipos o intentos', filas; END IF;

    RAISE NOTICE 'verify_equipos: alta pendiente, decision de la gerencia, marca fija, intentos de solo agregado y aislamiento verificados';
END $$;
ROLLBACK;
