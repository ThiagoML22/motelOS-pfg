-- Verifica el aislamiento entre establecimientos (migracion 006) y el registro de actividad (migracion 007) con el
-- rol de la aplicacion, motel_app: Row Level Security, claves foraneas compuestas, funciones de la plataforma y
-- reglas del registro. Falla con error si alguna garantia no se cumple. Corre en una transaccion que se revierte.
-- Uso: psql -v ON_ERROR_STOP=1 -d <base con las migraciones aplicadas> -f db/verify_multiinquilino.sql  (como dueno)
BEGIN;
DO $$
DECLARE
    otro integer;
    hab_otra integer;
    turno_otro uuid;
    conserje_otro integer;
    guardia_otra integer;
    gerencia_1 integer;
    conserje_1 integer;
    nuevo integer;
    entrada bigint;
    cantidad integer;
    filas integer;
    bloqueado boolean;
BEGIN
    -- Datos del dueno de las tablas: un segundo establecimiento con la habitacion 1, un conserje y un turno.
    INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-otro', 'Otro') RETURNING id INTO otro;
    INSERT INTO habitaciones (establecimiento_id, numero, estado) VALUES (otro, 1, 'Libre') RETURNING id INTO hab_otra;
    INSERT INTO tarifas (establecimiento_id, nombre, tarifa_base, tarifa_fraccion) VALUES (otro, 'Otra', 9000, 3000);
    INSERT INTO operadores (establecimiento_id, usuario, nombre_visible, hash_clave)
    VALUES (otro, 'conserje1', 'Conserje del otro', 'x') RETURNING id INTO conserje_otro;
    INSERT INTO guardias (establecimiento_id, operador_id, franja) VALUES (otro, conserje_otro, '06:00')
    RETURNING id INTO guardia_otra;
    INSERT INTO turnos (establecimiento_id, habitacion_id, tarifa_id, tarifa_base, total_general, estado,
                        operador_apertura_id, guardia_apertura_id)
    SELECT otro, hab_otra, t.id, 9000, 9000, 'Anulado', conserje_otro, guardia_otra
      FROM tarifas t WHERE t.establecimiento_id = otro
    RETURNING id INTO turno_otro;
    INSERT INTO operadores (establecimiento_id, usuario, nombre_visible, hash_clave, rol)
    VALUES (NULL, 'verif.plataforma', 'Plataforma', 'x', 'PLATAFORMA');
    PERFORM set_config('app.establecimiento_id', '1', true);
    INSERT INTO operadores (usuario, nombre_visible, hash_clave, rol)
    VALUES ('verif.gerencia', 'Gerencia', 'x', 'ADMINISTRADOR') RETURNING id INTO gerencia_1;
    INSERT INTO operadores (usuario, nombre_visible, hash_clave) VALUES ('verif.conserje', 'Conserje', 'x')
    RETURNING id INTO conserje_1;

    -- Claves compuestas: ni el dueno de las tablas cruza establecimientos (un pago del 1 sobre un turno del otro).
    bloqueado := false;
    BEGIN
        INSERT INTO estadias_activas (establecimiento_id, turno_id, identificador_vehicular) VALUES (1, turno_otro, 'X');
    EXCEPTION WHEN foreign_key_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Una fila del establecimiento 1 apunto a un turno de otro establecimiento'; END IF;

    SET LOCAL ROLE motel_app;

    -- 1. Con el establecimiento 1, motel_app no ve las filas del otro, aunque la consulta no filtre.
    PERFORM set_config('app.establecimiento_id', '1', true);
    SELECT count(*) INTO cantidad FROM habitaciones WHERE establecimiento_id = otro;
    IF cantidad <> 0 THEN RAISE EXCEPTION 'RLS: el establecimiento 1 vio habitaciones de otro'; END IF;
    SELECT count(*) INTO cantidad FROM turnos WHERE id = turno_otro;
    IF cantidad <> 0 THEN RAISE EXCEPTION 'RLS: el establecimiento 1 vio un turno de otro'; END IF;
    SELECT count(*) INTO cantidad FROM operadores WHERE usuario = 'conserje1' AND id = conserje_otro;
    IF cantidad <> 0 THEN RAISE EXCEPTION 'RLS: el establecimiento 1 vio un usuario de otro'; END IF;

    -- 2. Tampoco las modifica: el UPDATE no alcanza ninguna fila.
    UPDATE habitaciones SET estado = 'Mantenimiento' WHERE id = hab_otra;
    GET DIAGNOSTICS filas = ROW_COUNT;
    IF filas <> 0 THEN RAISE EXCEPTION 'RLS: el establecimiento 1 modifico una habitacion de otro'; END IF;

    -- 3. No inserta filas a nombre de otro establecimiento (WITH CHECK).
    bloqueado := false;
    BEGIN INSERT INTO habitaciones (establecimiento_id, numero, estado) VALUES (otro, 99, 'Libre');
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'RLS: el establecimiento 1 inserto una fila de otro'; END IF;

    -- 4. Sin establecimiento fijado no ve ninguna fila (falla cerrada) y no puede insertar.
    PERFORM set_config('app.establecimiento_id', '', true);
    SELECT count(*) INTO cantidad FROM habitaciones;
    IF cantidad <> 0 THEN RAISE EXCEPTION 'RLS: sin establecimiento se vieron % habitaciones', cantidad; END IF;
    SELECT count(*) INTO cantidad FROM operadores;
    IF cantidad <> 0 THEN RAISE EXCEPTION 'RLS: sin establecimiento se vieron usuarios'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO articulos (codigo, descripcion, precio_unitario, stock_actual) VALUES ('X', 'X', 1, 1);
    EXCEPTION WHEN foreign_key_violation OR insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Sin establecimiento se inserto un articulo'; END IF;

    -- 5. La plataforma (0) no ve la operacion de ningun establecimiento.
    PERFORM set_config('app.establecimiento_id', '0', true);
    SELECT count(*) INTO cantidad FROM turnos;
    IF cantidad <> 0 THEN RAISE EXCEPTION 'RLS: la plataforma vio turnos'; END IF;
    SELECT count(*) INTO cantidad FROM operadores WHERE rol <> 'PLATAFORMA';
    IF cantidad <> 0 THEN RAISE EXCEPTION 'RLS: la plataforma vio usuarios de un establecimiento'; END IF;
    -- La plataforma registra el acceso de sus usuarios, pero no crea usuarios (el rol queda en OPERADOR).
    UPDATE operadores SET ultimo_acceso = now() WHERE rol = 'PLATAFORMA';
    GET DIAGNOSTICS filas = ROW_COUNT;
    IF filas <> 1 THEN RAISE EXCEPTION 'La plataforma no pudo registrar el acceso de su usuario'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO operadores (establecimiento_id, usuario, nombre_visible, hash_clave)
          VALUES (NULL, 'verif.intrusa', 'X', 'x');
    EXCEPTION WHEN check_violation OR insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'La plataforma creo un usuario sin establecimiento'; END IF;
    -- pero si obtiene el resumen (solo cantidades) ...
    SELECT count(*) INTO cantidad FROM resumen_plataforma();
    IF cantidad < 2 THEN RAISE EXCEPTION 'El resumen de la plataforma no incluyo los establecimientos'; END IF;
    -- ... y da de alta un establecimiento con su gerencia inicial, una sola vez.
    INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-nuevo', 'Nuevo') RETURNING id INTO nuevo;
    PERFORM set_config('app.establecimiento_id', nuevo::text, true);
    INSERT INTO habitaciones (numero, estado) VALUES (1, 'Libre');
    INSERT INTO configuracion_caja (fondo_cambio) VALUES (25000);
    PERFORM crear_gerencia_inicial('gerencia', 'Gerencia nueva', 'x');
    SELECT count(*) INTO cantidad FROM operadores WHERE rol = 'ADMINISTRADOR';
    IF cantidad <> 1 THEN RAISE EXCEPTION 'La gerencia inicial no quedo en el establecimiento nuevo'; END IF;
    bloqueado := false;
    BEGIN PERFORM crear_gerencia_inicial('otro.gerente', 'Intruso', 'x');
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se creo una segunda gerencia en un establecimiento con usuarios'; END IF;

    -- 6. Un establecimiento no usa las funciones de la plataforma ni se da de alta solo.
    PERFORM set_config('app.establecimiento_id', '1', true);
    bloqueado := false;
    BEGIN PERFORM crear_gerencia_inicial('intruso', 'Intruso', 'x');
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'El establecimiento 1 agrego una gerencia con la funcion inicial'; END IF;
    bloqueado := false;
    BEGIN PERFORM * FROM resumen_plataforma();
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Un establecimiento obtuvo el resumen de la plataforma'; END IF;
    bloqueado := false;
    BEGIN INSERT INTO establecimientos (codigo, nombre) VALUES ('verif-pirata', 'Pirata');
    EXCEPTION WHEN insufficient_privilege THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Un establecimiento dio de alta otro establecimiento'; END IF;

    -- 7. La gerencia edita los datos de su establecimiento, no los de otro, y no se reactiva sola.
    UPDATE establecimientos SET telefono = '0000' WHERE id = 1;
    UPDATE establecimientos SET telefono = '0000' WHERE id = otro;
    GET DIAGNOSTICS filas = ROW_COUNT;
    IF filas <> 0 THEN RAISE EXCEPTION 'El establecimiento 1 modifico los datos de otro'; END IF;
    bloqueado := false;
    BEGIN UPDATE establecimientos SET activo = false WHERE id = 1;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Un establecimiento cambio su propia suspension'; END IF;

    -- 8. Registro de actividad: solo agregado; la revision la marca la gerencia, una vez.
    INSERT INTO registro_actividad (operador_id, categoria, accion, descripcion, requiere_revision)
    VALUES (conserje_1, 'INVENTARIO', 'ARTICULO_ALTA', 'Alta de verificacion', true) RETURNING id INTO entrada;
    bloqueado := false;
    BEGIN UPDATE registro_actividad SET descripcion = 'cambiada' WHERE id = entrada;
    EXCEPTION WHEN insufficient_privilege OR raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se modifico una entrada del registro de actividad'; END IF;
    bloqueado := false;
    BEGIN DELETE FROM registro_actividad WHERE id = entrada;
    EXCEPTION WHEN insufficient_privilege OR raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Se borro una entrada del registro de actividad'; END IF;
    bloqueado := false;
    BEGIN UPDATE registro_actividad SET revisado_por_id = conserje_1, revisado_en = now() WHERE id = entrada;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Un conserje marco una entrada como revisada'; END IF;
    UPDATE registro_actividad SET revisado_por_id = gerencia_1, revisado_en = now() WHERE id = entrada;
    bloqueado := false;
    BEGIN UPDATE registro_actividad SET revisado_por_id = gerencia_1, revisado_en = now() WHERE id = entrada;
    EXCEPTION WHEN raise_exception THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'Una entrada revisada se volvio a marcar'; END IF;
    bloqueado := false;
    BEGIN
        INSERT INTO registro_actividad (operador_id, categoria, accion, descripcion)
        VALUES (conserje_otro, 'INVENTARIO', 'X', 'Entrada a nombre de un usuario de otro establecimiento');
    EXCEPTION WHEN foreign_key_violation THEN bloqueado := true; END;
    IF NOT bloqueado THEN RAISE EXCEPTION 'El registro acepto un usuario de otro establecimiento'; END IF;

    RAISE NOTICE 'verify_multiinquilino: todas las garantias se cumplen';
END $$;
ROLLBACK;
