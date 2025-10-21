# Используем базовый образ с Chrome и ChromeDriver
FROM selenium/standalone-chrome:114.0

# Переключаемся в пользователя root для установки пакетов
USER root

# Устанавливаем зависимости для сборки Python 3.11
RUN apt-get update && apt-get install -y \
    wget \
    build-essential \
    zlib1g-dev \
    libffi-dev \
    libssl-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    libncursesw5-dev \
    libgdbm-dev \
    libnss3-dev \
    tk-dev \
    && rm -rf /var/lib/apt/lists/*

# Скачиваем, компилируем и устанавливаем Python 3.11
RUN wget https://www.python.org/ftp/python/3.11.6/Python-3.11.6.tgz \
    && tar -xvzf Python-3.11.6.tgz \
    && cd Python-3.11.6 \
    && ./configure --enable-optimizations \
    && make \
    && make install \
    && cd .. \
    && rm -rf Python-3.11.6.tgz Python-3.11.6

# Устанавливаем и обновляем pip
RUN python3.11 -m ensurepip --upgrade \
    && python3.11 -m pip install --upgrade pip setuptools wheel html5lib

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости проекта (requirements.txt)
COPY requirements.txt .

# Устанавливаем Python-зависимости
RUN python3.11 -m pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы проекта
COPY . .

# Устанавливаем переменные окружения для Selenium
ENV DISPLAY=:99

# Указываем точку входа
CMD ["python3.11", "main.py"]
